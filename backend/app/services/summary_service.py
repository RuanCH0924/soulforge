"""工作日志总结（记忆归纳）SummaryService（M16）。

把指定 Agent `memory/` 下某段日期范围的分散记录（每日文件 / 会话导出 / 主题碎片）
归纳成 **1 份**综述文档（五大章节 + 可选溯源表），规则契约来自外部 skill
`memory-summarize`（模式 A：月度 / 主题归纳）。

流程与 M15 日志标准化同构（方案见 docs/ARCHITECTURE.md「日志总结」）：

```
创建批次（幂等键 + 跨度上限）→ 后台生成计划（只读，绝不写盘）
→ 人工看完 diff 后确认写入（写前备份 + 写前验收 + 乐观锁）→ 验收报告
→（可选）确认汇总无误后清理源文件（移入系统回收站）
```

与 M15 的**刻意边界**：
- M15 是「同一天多来源 → 1 个日文件」的**逐日**归并（两表 + 逐日条目）；
  M16 是「一段时间的全部来源 → 1 份综述」的**单份**产物，因此只有批次表。
- M16 **默认不动任何源文件**（只读归纳）；清理源文件是汇总写入后单独触发的可选动作。
- 产物命名：整月 → `memory/YYYY-MM-记忆归纳.md`；否则 `memory/<起>_<止>-记忆归纳.md`。

护栏（与项目既有口径一致）：
- 强规则不过 / 有低价值元数据壳残留 → 不写入（`needs_review`，零污染）
- 乐观锁：计划生成时记录目标文件与全部来源的 SHA-256，写入前逐个比对 → 任何一项变了即 `409`
- 所有路径都是 Agent 相对路径，读写一律经 `FileManager`（内部过 `_safe_join`）
- 全局「关闭执行（只出计划）」开关：`config.summarizer.dry_run_only`
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import date as _date
from datetime import timedelta
from pathlib import Path

from loguru import logger

from app.config import Config
from app.core.errors import (
    BadRequestError,
    ConflictError,
    SummaryRunDisabledError,
    SummaryRunNotFoundError,
    SummaryRunStatusError,
    SummarySourceTooLargeError,
    UnsafePathError,
)
from app.models.db import Database, SummaryRunRow
from app.models.schemas import (
    FormatReport,
    LintWarning,
    SummaryRun,
    SummaryRunCleanupResult,
    SummaryRunCreate,
    SummaryRunCreateResult,
    SummaryRunReport,
    SummaryRunSummary,
    SummarySourceInfo,
)
from app.services.audit_service import AuditService
from app.services.daily_merge_service import (
    CHUNK_TARGET_BYTES,
    KIND_LABEL,
    MAX_CHUNKS_PER_SOURCE,
    sha256_text,
)
from app.services.daily_preprocessor import (
    PreprocessedSource,
    describe_shells,
    detect_residual_shells,
    preprocess_source,
)
from app.services.daily_source_scanner import MEMORY_DIR, DailySourceScanner, classify_daily_filename
from app.services.diff_service import render_html_diff, unified_diff
from app.services.file_manager import FileManager
from app.services.format_validator import FormatValidator
from app.services.lint_service import LintService
from app.services.llm_registry import LLMRegistry, LLMResponse
from app.services.preset_service import PresetService
from app.services.template_rules import TemplateRules, template_rule_summary

# 批次状态机（见 docs/DATA-MODEL.md）
RUN_PLANNED = "planned"          # 已创建，正在归纳（也包含「刚建、还没开跑」）
RUN_AWAITING = "awaiting_confirm"
RUN_APPLIED = "applied"
RUN_NEEDS_REVIEW = "needs_review"
RUN_REJECTED = "rejected"
RUN_FAILED = "failed"
RUN_EMPTY = "empty"              # 该范围没有可归纳的来源

# 终态：命中幂等键时可另起新批次重试（复用只发生在非终态）
_TERMINAL_RUNS = (RUN_FAILED, RUN_REJECTED)

# 单次归纳的来源数上限（防失控；与天数上限是两道独立的护栏）
MAX_SOURCES = 180
# 归纳 prompt 体积上限：超了说明来源太多太大，转人工复核而不是硬烧 token
MAX_PROMPT_BYTES = 200 * 1024


def _is_full_month(date_from: str, date_to: str) -> bool:
    """该范围是否恰好是一整个自然月（决定产物命名用 `YYYY-MM`）。"""
    year, month = date_from[:4], date_from[5:7]
    if date_to[:7] != f"{year}-{month}" or date_from[8:] != "01":
        return False
    first = _date(int(year), int(month), 1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return date_to == last.isoformat()


def output_path_for(date_from: str, date_to: str) -> str:
    """归纳产物的目标路径：整月 → `memory/YYYY-MM-记忆归纳.md`，否则 `memory/<起>_<止>-记忆归纳.md`。"""
    if _is_full_month(date_from, date_to):
        return f"{MEMORY_DIR}/{date_from[:7]}-记忆归纳.md"
    return f"{MEMORY_DIR}/{date_from}_{date_to}-记忆归纳.md"


def title_span_for(date_from: str, date_to: str) -> str:
    """产物 H1 里的时间段文案（与命名口径一致）。"""
    return date_from[:7] if _is_full_month(date_from, date_to) else f"{date_from} ~ {date_to}"


def _split_chunks(text: str, target_bytes: int = CHUNK_TARGET_BYTES) -> list[str]:
    """按行切块（只在行边界断开，保证不切碎行、每块体积有界）。"""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        line_bytes = len(line.encode("utf-8")) + 1
        if current and size + line_bytes > target_bytes:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += line_bytes
    if current:
        chunks.append("\n".join(current))
    return chunks


SYSTEM_PROMPT = (
    "你是 Soulforge 的记忆归纳助手。把一段时间的分散记录归纳成一份单一综述："
    "按「完成的工作 / 经验教训 / 重要决定 / 重要信息 / 待办事项」五大章节归类；"
    "丢弃每天重复的流水账与调试中间态，只保留有长期检索价值的事实、决定与待办；"
    "同一信息在多日反复出现时只保留最新口径。"
    "禁止在输出中写任何来源说明（「附录：溯源对照表」里的来源列除外）。"
    "输出必须 100% 符合格式规则；正文只输出 Markdown 文档。"
    "不要输出思考过程、任务分析、规则复述或任何对话性文字，第一行直接进入文档标题。"
)

CHUNK_PROMPT_TEMPLATE = """【任务】下面是归纳来源「{path}」的第 {index}/{total} 段。
请按「风格与内容规则」把它提炼成事实清单（保留结论、决定与可复用数据，删除过程噪音），供后续归纳使用。

【风格与内容规则（来自预设，必须逐条遵守）】
{style_block}

【输出要求】
只输出提炼后的 Markdown 片段，不要输出任何说明、总结语或对任务的复述；
不要写来源、不要写「本段」「以下是」这类话；不要用代码围栏包裹。

【本段原文】
{chunk}"""


class SummaryService:
    """工作日志总结批次：创建 → 生成计划 → 确认写入 → 验收 →（可选）清理源文件。"""

    def __init__(self, db: Database, config: Config, file_manager: FileManager, presets: PresetService,
                 llm: LLMRegistry, lint: LintService, audit: AuditService,
                 scanner: DailySourceScanner):
        self.db = db
        self.config = config
        self.file_manager = file_manager
        self.presets = presets
        self.llm = llm
        self.lint = lint
        self.audit = audit
        self.scanner = scanner

    # ---------- 查询 ----------

    @staticmethod
    def _row_to_summary(row: SummaryRunRow) -> SummaryRunSummary:
        return SummaryRunSummary(
            id=row.id, agent_id=row.agent_id, date_from=row.date_from, date_to=row.date_to,
            preset_id=row.preset_id, preset_version=row.preset_version, provider_id=row.provider_id,
            status=row.status, output_path=row.output_path, source_count=row.source_count,
            token_budget=row.token_budget, tokens_used=row.tokens_used,
            cost_estimate_usd=row.cost_estimate_usd, error=row.error, cleanup_at=row.cleanup_at,
            created_at=row.created_at, updated_at=row.updated_at, finished_at=row.finished_at,
        )

    @staticmethod
    def _row_to_detail(row: SummaryRunRow) -> SummaryRun:
        cleanup = _load_json(row.cleanup_json) or {}
        fmt = _load_json(row.format_report_json)
        return SummaryRun(
            **SummaryService._row_to_summary(row).model_dump(),
            extra_instructions=row.extra_instructions,
            sources=[SummarySourceInfo(**s) for s in (_load_json(row.sources_json) or [])],
            output_content=row.output_content, unified_diff=row.unified_diff,
            html_diff=render_html_diff(row.unified_diff) if row.unified_diff else None,
            format_report=FormatReport(**fmt) if fmt else FormatReport(ok=False),
            lint_warnings=[LintWarning(**w) for w in (_load_json(row.lint_warnings_json) or [])],
            notes=_load_json(row.notes_json) or [],
            backup_id=row.backup_id, applied_at=row.applied_at,
            deleted_sources=cleanup.get("deleted", []), failed_sources=cleanup.get("failed", []),
        )

    def _get_row(self, session, run_id: str) -> SummaryRunRow:
        row = session.get(SummaryRunRow, run_id)
        if row is None:
            raise SummaryRunNotFoundError(f"归纳批次不存在：{run_id}", details={"run_id": run_id})
        return row

    def list(self, agent_id: str | None = None, status: str | None = None,
             limit: int = 50) -> list[SummaryRunSummary]:
        with self.db.session() as s:
            q = s.query(SummaryRunRow)
            if agent_id:
                q = q.filter(SummaryRunRow.agent_id == agent_id)
            if status:
                q = q.filter(SummaryRunRow.status == status)
            rows = q.order_by(SummaryRunRow.created_at.desc()).limit(limit).all()
            return [self._row_to_summary(r) for r in rows]

    def get(self, run_id: str) -> SummaryRun:
        with self.db.session() as s:
            return self._row_to_detail(self._get_row(s, run_id))

    def _update_run(self, run_id: str, **fields) -> None:
        with self.db.session() as s:
            row = self._get_row(s, run_id)
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = int(time.time())
            s.commit()

    # ---------- 创建 ----------

    @staticmethod
    def _validate_date(label: str, value: str) -> str:
        """日期参数校验：路径穿越 → 403；非法日期 → 400。"""
        if not value or any(ch in value for ch in ("/", "\\")) or ".." in value:
            raise UnsafePathError(f"{label} 含非法路径字符：{value!r}", details={label: value})
        if classify_daily_filename(f"{value}.md") is None:
            raise BadRequestError(f"{label} 必须是合法的 YYYY-MM-DD 日期", details={label: value})
        return value

    def _collect_sources(self, agent_id: str, date_from: str, date_to: str) -> list[dict]:
        """按日期范围收集可归纳的来源（`memory/` 顶层的 A/B/C 类日文件，按日期升序）。"""
        groups = self.scanner.scan_range(agent_id, date_from, date_to)
        return [
            {"path": s.path, "date": g.date, "kind": s.kind, "raw_bytes": s.size_bytes,
             "clean_bytes": s.size_bytes, "removed_total": 0, "summarized": False, "chunks": 0}
            for g in groups for s in g.sources
        ]

    def _source_hashes(self, agent_id: str, paths: list[str]) -> dict[str, str]:
        """计划生成时的乐观锁基线：全部来源 + 目标文件的 SHA-256（缺失记空串）。"""
        hashes: dict[str, str] = {}
        for path in paths:
            try:
                hashes[path] = sha256_text(self.file_manager.read_text(agent_id, path))
            except Exception:
                hashes[path] = ""
        return hashes

    @staticmethod
    def _idempotency_key(agent_id: str, date_from: str, date_to: str, preset_id: str,
                         preset_version: int, provider_id: str, output_path: str,
                         hashes: dict[str, str]) -> str:
        """批次键：与来源与目标内容绑定——同范围同内容重复提交直接复用，不再调 LLM。"""
        parts = [agent_id, date_from, date_to, preset_id, str(preset_version), provider_id, output_path]
        for path in sorted(hashes):
            parts.append(f"{path}:{hashes[path]}")
        return sha256_text("|".join(parts))

    async def create(self, payload: SummaryRunCreate) -> SummaryRunCreateResult:
        """创建批次（异步执行）：校验 → 幂等复用 → 落库 → 后台生成归纳计划。"""
        agent_id = payload.agent_id
        self.file_manager.require_agent(agent_id)
        date_from = self._validate_date("date_from", payload.date_from)
        date_to = self._validate_date("date_to", payload.date_to)
        if date_from > date_to:
            raise BadRequestError("date_from 不能晚于 date_to",
                                  details={"date_from": date_from, "date_to": date_to})
        preset = self.presets.get(payload.preset_id)          # 不存在 → 404
        self.llm.get_provider(payload.provider_id)            # 不存在/禁用 → 404

        cfg = self.config.summarizer
        span_days = (_date.fromisoformat(date_to) - _date.fromisoformat(date_from)).days + 1
        if span_days > cfg.max_days_per_run:
            raise BadRequestError(
                f"该范围跨 {span_days} 天，超过单次归纳上限 {cfg.max_days_per_run} 天，请缩小范围",
                details={"days": span_days, "max_days_per_run": cfg.max_days_per_run})

        entries = self._collect_sources(agent_id, date_from, date_to)
        if len(entries) > MAX_SOURCES:
            raise BadRequestError(
                f"该范围有 {len(entries)} 个来源，超过单次上限 {MAX_SOURCES} 个，请缩小范围",
                details={"sources": len(entries), "max_sources": MAX_SOURCES})

        output_path = output_path_for(date_from, date_to)
        hashes = self._source_hashes(agent_id, [e["path"] for e in entries] + [output_path])
        key = self._idempotency_key(agent_id, date_from, date_to, preset.id, preset.version,
                                    payload.provider_id, output_path, hashes)
        now = int(time.time())
        with self.db.session() as s:
            existing = (s.query(SummaryRunRow)
                        .filter(SummaryRunRow.idempotency_key == key)
                        .order_by(SummaryRunRow.created_at.desc()).first())
            if existing is not None and existing.status not in _TERMINAL_RUNS:
                return SummaryRunCreateResult(
                    run_id=existing.id, status=existing.status, source_count=existing.source_count,
                    reused=True, created_at=existing.created_at)

            run_id = f"run-{uuid.uuid4().hex}"
            status = RUN_PLANNED if entries else RUN_EMPTY
            s.add(SummaryRunRow(
                id=run_id, agent_id=agent_id, date_from=date_from, date_to=date_to,
                preset_id=preset.id, preset_version=preset.version, provider_id=payload.provider_id,
                status=status, idempotency_key=key, extra_instructions=payload.extra_instructions,
                output_path=output_path, source_count=len(entries),
                source_hashes_json=json.dumps(hashes, ensure_ascii=False),
                sources_json=json.dumps(entries, ensure_ascii=False),
                token_budget=cfg.token_budget,
                error=None if entries else "该日期范围内没有可归纳的记录（memory/ 顶层没有符合日文件名模式的 .md）",
                created_at=now, updated_at=now, finished_at=None if entries else now,
            ))
            s.commit()

        self.audit.record("summary_run_create", agent_id, output_path, {
            "run_id": run_id, "sources": len(entries), "date_from": date_from, "date_to": date_to,
            "preset_id": preset.id, "preset_version": preset.version, "provider_id": payload.provider_id,
            "output_path": output_path, "token_budget": cfg.token_budget,
        })
        if entries:
            asyncio.create_task(self.execute(run_id))
        return SummaryRunCreateResult(run_id=run_id, status=status, source_count=len(entries),
                                      reused=False, created_at=now)

    # ---------- 生成（后台） ----------

    @staticmethod
    def _style_block(preset) -> str:
        rules = list(preset.style_rules)
        if not rules:
            return "（无）"
        return "\n".join(f"{i}. {line}" for i, line in enumerate(rules, start=1))

    async def _summarize_oversized(self, client, style_block: str, source: PreprocessedSource,
                                   chunks: list[str], usage: list[LLMResponse]) -> PreprocessedSource:
        """超限来源 → 分块摘要；块数超上限则抛错转人工复核。"""
        if len(chunks) > MAX_CHUNKS_PER_SOURCE:
            raise SummarySourceTooLargeError(
                f"来源 {source.path} 净化后仍为 {source.clean_bytes // 1024}KB、需切成 {len(chunks)} 块，"
                f"超过单来源上限 {MAX_CHUNKS_PER_SOURCE} 块——本次转人工复核（不做无上限的 token 消耗）",
                details={"path": source.path, "clean_bytes": source.clean_bytes,
                         "chunks": len(chunks), "max_chunks": MAX_CHUNKS_PER_SOURCE})
        parts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            prompt = CHUNK_PROMPT_TEMPLATE.format(
                path=source.path, index=index, total=len(chunks),
                style_block=style_block, chunk=chunk)
            resp = await client.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            usage.append(resp)
            parts.append(resp.content.strip())
        return PreprocessedSource(
            path=source.path, kind=source.kind, text="\n\n".join(parts),
            raw_bytes=source.raw_bytes, rule_counts=source.rule_counts, summarized=True,
        )

    def _build_prompts(self, preset, rules: TemplateRules, date_from: str, date_to: str,
                       output_path: str, prepared: list[tuple], extra_instructions: str | None,
                       ) -> tuple[str, str]:
        """组装 `(system_prompt, user_prompt)`。

        来源在 prompt 内带日期与类型标签（模型需要据此判断优先级与去重），
        但输出要求里明确禁止把来源写进结果（溯源对照表除外）。
        """
        span = title_span_for(date_from, date_to)
        blocks = []
        for day, entry, pre in prepared:
            note = "（已分块摘要）" if pre.summarized else ""
            blocks.append(
                f"【来源：{entry['path']}（{day} · {KIND_LABEL.get(entry['kind'], entry['kind'])}）{note}】\n"
                f"```markdown\n{pre.text}\n```"
            )
        user_prompt = f"""【任务】把 {date_from} ~ {date_to} 这段范围内的分散记录归纳成一份**单一**综述文档，严格遵循：
第一步：读取并解析格式化规则与风格与内容规则；
第二步：通读全部来源（已按日期升序排列，每个来源都标注了日期）；
第三步：丢弃低价值内容——每天重复的流水账 / 反思模板、临时性小任务、调试中间态、同一时段的重复记录，只保留最终结论；
第四步：按五大主章节归类（完成的工作 / 经验教训 / 重要决定 / 重要信息 / 待办事项）；
        同一信息在多日反复出现时只保留最新、最全的一条；有长期价值的教训必须加粗；
第五步：自查输出，确保 100% 符合规则后再交付。

【本次归纳目标】
- 目标文件：{output_path}（命名与结构由强规则校验，必须严格合规）
- 第一行必须是 `# {span} 记忆归纳`
- 输出中不得出现任何来源说明行（「附录：溯源对照表」里的来源列除外）

【格式化规则（来自模板文档，必须逐条遵守）】
{template_rule_summary(rules)}

【风格与内容规则（来自预设，必须逐条遵守）】
{self._style_block(preset)}

【模板文档全文（含章节骨架示例，归纳时按此结构组织）】
```markdown
{preset.template_md or '（该预设未提供模板文档，以上规则即全部要求）'}
```

【附加指令】（老板可选）
{extra_instructions or '无'}

【本次来源（共 {len(prepared)} 个）】
{chr(10).join(blocks)}

【输出】只输出归纳后的 Markdown 文档正文，严格遵守：
1. 第一行必须是 `# {span} 记忆归纳`；
2. 必须按顺序包含且只包含五个二级章节：
   `## 一、完成的工作` / `## 二、经验教训` / `## 三、重要决定` / `## 四、重要信息` / `## 五、待办事项`；
3. 经验教训与重要决定建议用「| 日期 | … |」表格；待办用 `- [ ]`；内容宁可完整，不为精简而丢事实；
4. 末尾可附 `## 附录：溯源对照表`（内容 ← 来源日期）；没有可溯源内容时可省略；
5. 禁止输出思考过程、任务分析、步骤说明、规则复述、前言/结语、致谢等任何对话性文字；
6. 禁止用 ``` 代码围栏包裹整篇文档（文档内部的代码块不受此限）；
7. 所有大小标题使用中文。"""
        return SYSTEM_PROMPT, user_prompt

    async def execute(self, run_id: str) -> None:
        """后台生成归纳计划（只读，不写盘）：读来源 → 剥壳 / 分块摘要 → LLM → 强规则校验 → 落库。"""
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status != RUN_PLANNED:
                return
            agent_id = run.agent_id
            date_from, date_to = run.date_from, run.date_to
            preset_id, provider_id = run.preset_id, run.provider_id
            extra, output_path = run.extra_instructions, run.output_path
            entries = _load_json(run.sources_json) or []
            budget = run.token_budget

        try:
            preset = self.presets.get(preset_id)
            rules = self.presets.rules_for(preset)
            client = self.llm.get_client(provider_id)
            style_block = self._style_block(preset)
            usage: list[LLMResponse] = []
            prepared: list[tuple] = []
            reports: list[dict] = []
            notes: list[str] = []
            for entry in entries:
                raw = self.file_manager.read_text(agent_id, entry["path"])
                pre = preprocess_source(entry["path"], entry["kind"], raw)
                chunk_count = 0
                if pre.oversized:
                    chunks = _split_chunks(pre.text)
                    chunk_count = len(chunks)
                    logger.info(
                        f"来源超限转分块摘要：{entry['path']}（{pre.clean_bytes // 1024}KB，{chunk_count} 块）")
                    pre = await self._summarize_oversized(client, style_block, pre, chunks, usage)
                    notes.append(f"{entry['path']} 净化后仍超限，已分 {chunk_count} 块摘要后归纳")
                prepared.append((entry["date"], entry, pre))
                reports.append({
                    "path": entry["path"], "date": entry["date"], "kind": entry["kind"],
                    "raw_bytes": pre.raw_bytes, "clean_bytes": pre.clean_bytes,
                    "removed_total": pre.removed_total, "summarized": pre.summarized,
                    "chunks": chunk_count,
                })

            system_prompt, prompt = self._build_prompts(
                preset, rules, date_from, date_to, output_path, prepared, extra)
            prompt_bytes = len(prompt.encode("utf-8"))
            if prompt_bytes > MAX_PROMPT_BYTES:
                raise SummarySourceTooLargeError(
                    f"归纳 prompt 达 {prompt_bytes // 1024}KB，超过上限 {MAX_PROMPT_BYTES // 1024}KB"
                    "——本次来源过多，转人工复核",
                    details={"agent_id": agent_id, "prompt_bytes": prompt_bytes})

            resp = await client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ])
            usage.append(resp)

            sanitized, preamble = FormatValidator().sanitize(resp.content.strip())
            if preamble:
                logger.warning(f"归纳输出含前言，已剥离（{agent_id}）：{preamble[:120]!r}")
            output, format_report = FormatValidator().validate_and_fix(sanitized, rules)

            try:
                current = self.file_manager.read_text(agent_id, output_path)
            except Exception:
                current = ""
            diff = unified_diff(
                current, output,
                fromfile=f"{agent_id}/{output_path}（归纳前）",
                tofile=f"{agent_id}/{output_path}（归纳后）")
            tokens = sum(r.usage.total_tokens for r in usage)
            if budget and tokens > budget:
                notes.append(f"本次实际消耗 {tokens} tokens，已超出单次预算 {budget}（单次归纳为一次性调用，不中途截断）")

            ok = format_report.ok
            self._update_run(
                run_id,
                status=RUN_AWAITING if ok else RUN_FAILED,
                error=None if ok else "强规则校验未通过（章节缺失 / 顺序错误 / 禁用项），未写入任何文件",
                sources_json=json.dumps(reports, ensure_ascii=False),
                output_content=output, unified_diff=diff,
                format_report_json=json.dumps(format_report.model_dump(), ensure_ascii=False),
                lint_warnings_json=json.dumps(
                    [w.model_dump() for w in self.lint.lint_file(agent_id, output_path, output)],
                    ensure_ascii=False),
                notes_json=json.dumps(notes, ensure_ascii=False),
                prompt_tokens=sum(r.usage.prompt_tokens for r in usage),
                completion_tokens=sum(r.usage.completion_tokens for r in usage),
                tokens_used=tokens,
                cost_estimate_usd=round(sum(r.cost_estimate_usd for r in usage), 6),
                finished_at=int(time.time()),
            )
            logger.info(f"归纳批次 {run_id} 计划生成完成：{len(entries)} 个来源，{tokens} tokens")
        except Exception as e:  # 单次归纳失败：整批标 failed，不写任何文件
            logger.warning(f"归纳批次 {run_id} 生成失败：{e}")
            self._update_run(run_id, status=RUN_FAILED, error=str(e), finished_at=int(time.time()))

    # ---------- 确认 / 执行 ----------

    @staticmethod
    def _acceptance_error(content: str, rules: TemplateRules) -> str | None:
        """写前验收：强规则 ok 且低价值元数据壳（M01~M10）残留 = 0。返回错误说明，None = 通过。"""
        report = FormatValidator().validate(content, rules)
        if not report.ok:
            first = report.violations[0]
            return (f"强规则未通过（{len(report.violations)} 项，如 {first.rule_id} "
                    f"第 {first.line} 行：{first.message}）")
        residue = detect_residual_shells(content)
        if residue:
            return f"仍残留低价值元数据壳：{describe_shells(residue)}"
        return None

    def _lock_conflict(self, agent_id: str, path: str, expected: str) -> str | None:
        """乐观锁：目标文件当前内容必须与计划生成时一致。返回冲突说明，None = 一致。"""
        try:
            actual = sha256_text(self.file_manager.read_text(agent_id, path))
        except Exception:
            actual = ""
        if actual == expected:
            return None
        if expected and not actual:
            return f"{path} 已被外部删除（计划基于其旧内容）"
        if not expected:
            return f"{path} 已被外部创建（计划本要新建它）"
        return f"{path} 已被外部修改（计划基于旧版本）"

    def reject(self, run_id: str) -> SummaryRun:
        """拒绝批次（不写入任何文件）。"""
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status not in (RUN_PLANNED, RUN_AWAITING):
                raise SummaryRunStatusError(
                    f"仅 planned / awaiting_confirm 状态可拒绝，当前为 {run.status}",
                    details={"run_id": run_id, "status": run.status})
            run.status = RUN_REJECTED
            run.finished_at = int(time.time())
            run.updated_at = int(time.time())
            s.commit()
        self.audit.record("summary_run_reject", None, None, {"run_id": run_id})
        return self.get(run_id)

    def apply(self, run_id: str) -> SummaryRun:
        """确认写入：写前验收 + 乐观锁 → 写入汇总文件（备份 + 审计）→ 验收。

        源文件默认**不动**；清理源文件走 `cleanup_sources()` 单独触发。
        """
        if self.config.summarizer.dry_run_only:
            raise SummaryRunDisabledError(
                "执行已被全局开关关闭（config.toml 的 summarizer.dry_run_only=true），当前只能出计划",
                details={"run_id": run_id})

        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status != RUN_AWAITING:
                raise SummaryRunStatusError(
                    f"仅 awaiting_confirm 状态可写入，当前为 {run.status}",
                    details={"run_id": run_id, "status": run.status})
            agent_id, preset_id = run.agent_id, run.preset_id
            output_path = run.output_path
            content = run.output_content or ""
            expected = (_load_json(run.source_hashes_json) or {}).get(output_path, "")

        if not content:
            self._update_run(run_id, status=RUN_NEEDS_REVIEW, error="该批次没有生成内容（计划缺失）")
            return self.get(run_id)

        rules = self.presets.rules_for(self.presets.get(preset_id))
        problem = self._acceptance_error(content, rules)
        if problem:
            self._update_run(run_id, status=RUN_NEEDS_REVIEW, error=problem)
            self.audit.record("summary_blocked", agent_id, output_path,
                              {"run_id": run_id, "reason": problem}, result="failed")
            return self.get(run_id)

        conflict = self._lock_conflict(agent_id, output_path, expected)
        if conflict:
            self._update_run(run_id, status=RUN_FAILED, error=conflict)
            raise ConflictError(
                f"目标文件已被外部改动，本次未写入任何文件；请重新生成计划：{conflict}",
                details={"run_id": run_id, "output_path": output_path, "reason": conflict})

        result = self.file_manager.write(agent_id, output_path, content,
                                         reason="memory-summarize", audit=False)
        now = int(time.time())
        self._update_run(run_id, status=RUN_APPLIED, applied_at=now,
                         backup_id=result.backup_id, error=None, finished_at=now)
        self.audit.record("summary_apply", agent_id, output_path, {
            "run_id": run_id, "output_path": output_path, "backup_id": result.backup_id,
        })
        report = self.build_report(run_id)
        if not report.passed:
            self._update_run(run_id, status=RUN_NEEDS_REVIEW)
        return self.get(run_id)

    def cleanup_sources(self, run_id: str) -> SummaryRunCleanupResult:
        """清理源文件（可选动作）：把该批次范围内的源文件移入系统回收站。

        仅在汇总文件**已写入**且未清理过时可调用；产物本身永不删除。
        """
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.applied_at is None:
                raise SummaryRunStatusError(
                    "只有汇总文件已写入的批次才能清理源文件",
                    details={"run_id": run_id, "status": run.status})
            if run.cleanup_at is not None:
                raise SummaryRunStatusError("该批次的源文件已经清理过，无需重复执行",
                                            details={"run_id": run_id})
            agent_id, output_path = run.agent_id, run.output_path
            entries = _load_json(run.sources_json) or []

        deleted: list[str] = []
        failed: list[str] = []
        for entry in entries:
            if entry["path"] == output_path:  # 安全：绝不删产物自身
                continue
            try:
                self.file_manager.delete(agent_id, entry["path"])
                deleted.append(entry["path"])
            except Exception as e:
                failed.append(f"{entry['path']}：{e}")
        self._update_run(run_id, cleanup_at=int(time.time()),
                         cleanup_json=json.dumps({"deleted": deleted, "failed": failed},
                                                 ensure_ascii=False))
        self.audit.record("summary_cleanup_sources", agent_id, output_path, {
            "run_id": run_id, "deleted": deleted, "failed": failed,
        }, result="failed" if failed else "ok")
        return SummaryRunCleanupResult(run_id=run_id, deleted=deleted, failed=failed)

    # ---------- 验收报告 ----------

    def build_report(self, run_id: str) -> SummaryRunReport:
        """对磁盘上的**真实文件**做验收核对，只读、可重复跑。

        核对五项：汇总文件已交付 / 命名合规 / 必填章节齐全 / 无低价值壳残留 / 源文件状态自洽。
        """
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            agent_id = run.agent_id
            output_path = run.output_path
            date_from, date_to = run.date_from, run.date_to
            delivered = run.applied_at is not None
            cleanup_at = run.cleanup_at
            entries = _load_json(run.sources_json) or []
            error = run.error
            status = run.status
            preset_id = run.preset_id
            tokens, cost = run.tokens_used, run.cost_estimate_usd
        workspace = Path(self.file_manager.require_agent(agent_id).workspace)
        details: list[str] = []
        naming_ok = output_path == output_path_for(date_from, date_to)
        if not naming_ok:
            details.append(f"命名不合规：{output_path}")

        sections_ok = no_residue = False
        if not delivered:
            details.append(error or f"未交付（{status}）")
        else:
            try:
                rules = self.presets.rules_for(self.presets.get(preset_id))
            except Exception as e:
                details.append(f"预设读不到，无法核对章节：{e}")
                rules = None
            try:
                content = self.file_manager.read_text(agent_id, output_path)
            except Exception as e:
                details.append(f"汇总文件读不到：{e}")
            else:
                if rules is not None:
                    report = FormatValidator().validate(content, rules)
                    sections_ok = report.ok
                    if not report.ok:
                        details.append("章节校验未通过：" + "；".join(
                            f"{v.rule_id}(第 {v.line} 行) {v.message}" for v in report.violations[:3]))
                residue = detect_residual_shells(content)
                no_residue = not residue
                if residue:
                    details.append(f"仍有低价值元数据壳：{describe_shells(residue)}")

        # 源文件状态自洽：未清理时都应仍在；已清理时都不应仍在
        source_paths = [e["path"] for e in entries if e["path"] != output_path]
        if cleanup_at is None:
            missing = [p for p in source_paths if not (workspace / p).exists()]
            sources_ok = not missing
            if missing:
                details.append("源文件已不存在（被外部改动或手工删除）：" + "、".join(missing))
        else:
            leftovers = [p for p in source_paths if (workspace / p).exists()]
            sources_ok = not leftovers
            if leftovers:
                details.append("声明已清理但仍在磁盘上的源文件：" + "、".join(leftovers))

        passed = (delivered and naming_ok and sections_ok and no_residue and sources_ok)
        return SummaryRunReport(
            run_id=run_id, agent_id=agent_id, status=status, passed=passed,
            output_path=output_path, delivered=delivered, naming_ok=naming_ok,
            sections_ok=sections_ok, no_residue=no_residue, sources_ok=sources_ok,
            tokens_used=tokens, cost_estimate_usd=cost,
            generated_at=int(time.time()), details=details,
        )


def _load_json(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
