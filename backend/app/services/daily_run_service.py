"""工作日志标准化批次 DailyRunService（M15 · P2）。

流程（方案 §6.2，P2 覆盖第 1 / 6 / 7 / 8 步）：

```
创建批次（幂等键 + 天数上限）→ 后台逐日生成计划（复用 P1 的 DailyMergeService）
→ 人工逐个 diff 确认（可整批确认 / 跳过某日）→ 写入日文件（写前备份 + 审计 + 乐观锁）
→ 删除碎片（走系统回收站）→ 跑 Verifier 出验收报告
```

**护栏**（方案 §8.5，均有测试守着）：

- 单批**天数上限** + 单批 **token 预算**越限即中止（不做「打满预算继续跑」）
- **写前验收**：强规则 ok 且低价值元数据壳（M01~M10）残留 = 0 才允许写入；不过则该日 `blocked`，
  **不写入、也不删碎片**（零污染）
- **乐观锁**：计划生成时记录目标文件与全部来源的 SHA-256；应用前逐个比对，
  任何一项变了 → `409`（同时覆盖「同一天两个批次并发确认」与「计划生成后被外部改动」）
- 所有读写经 `FileManager`（内部 `_safe_join`）；碎片删除走 `send2trash` 可恢复
- 全局「关闭执行（只出计划）」开关：`config.daily_standardizer.dry_run_only`

**与 M13 的关系**：`ai_jobs` 保持「单文件」语义不变，批次用独立两表，互不污染状态机。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from loguru import logger

from app.config import Config
from app.core.errors import (
    BadRequestError,
    ConflictError,
    DailyRunDisabledError,
    DailyRunNotFoundError,
    DailyRunStatusError,
    UnsafePathError,
)
from app.models.db import DailyRunItemRow, DailyRunRow, Database
from app.models.schemas import (
    DailyRun,
    DailyRunApplyRequest,
    DailyRunApplyResult,
    DailyRunCreate,
    DailyRunCreateResult,
    DailyRunItem,
    DailyRunReport,
    DailyRunReportItem,
    DailyRunSummary,
    DailySourceInfo,
    FormatReport,
    LintWarning,
)
from app.services.audit_service import AuditService
from app.services.daily_merge_service import DailyMergePlan, DailyMergeService, sha256_text
from app.services.daily_preprocessor import describe_shells, detect_residual_shells
from app.services.daily_source_scanner import DailySourceScanner, DayGroup, classify_daily_filename
from app.services.diff_service import render_html_diff
from app.services.file_manager import FileManager
from app.services.format_validator import FormatValidator
from app.services.llm_registry import LLMRegistry
from app.services.preset_service import PresetService

# 批次状态机（见 docs/DATA-MODEL.md 2.9）
RUN_PLANNED = "planned"          # 已创建，正在逐日生成计划（也包含「刚建、还没开跑」）
RUN_AWAITING = "awaiting_confirm"
RUN_APPLIED = "applied"
RUN_PARTIAL = "partially_applied"
RUN_NEEDS_REVIEW = "needs_review"
RUN_REJECTED = "rejected"
RUN_FAILED = "failed"
RUN_EMPTY = "empty"              # 该范围没有需要整理的日子

# 逐日条目状态
ITEM_PENDING = "pending"         # 还没轮到生成
ITEM_PLANNED = "planned"         # 计划已生成，等确认
ITEM_FAILED = "failed"           # 生成失败 / 强规则没过
ITEM_BLOCKED = "blocked"         # 写前验收不过 → 未写入
ITEM_APPLIED = "applied"
ITEM_PARTIAL = "partially_applied"   # 日文件已写，碎片删失败
ITEM_SKIPPED = "skipped"
# 模型判定「本日无可归档内容」：不产出日文件（该日没有值得留存的内容），
# 只清理 B/C 碎片；A 类主文件 memory/YYYY-MM-DD.md 保持不动。
ITEM_EMPTY = "empty"

_TERMINAL_RUNS = (RUN_FAILED, RUN_REJECTED)


class DailyRunService:
    """工作日志标准化批次：创建 → 生成计划 → 确认 → 执行 → 验收。"""

    def __init__(self, db: Database, config: Config, file_manager: FileManager, presets: PresetService,
                 llm: LLMRegistry, audit: AuditService, merge: DailyMergeService,
                 scanner: DailySourceScanner):
        self.db = db
        self.config = config
        self.file_manager = file_manager
        self.presets = presets
        self.llm = llm
        self.audit = audit
        self.merge = merge
        self.scanner = scanner

    # ---------- 查询 ----------

    @staticmethod
    def _row_to_summary(row: DailyRunRow) -> DailyRunSummary:
        return DailyRunSummary(
            id=row.id, agent_id=row.agent_id, date_from=row.date_from, date_to=row.date_to,
            preset_id=row.preset_id, preset_version=row.preset_version, provider_id=row.provider_id,
            status=row.status, days_total=row.days_total, token_budget=row.token_budget,
            tokens_used=row.tokens_used, cost_estimate_usd=row.cost_estimate_usd, error=row.error,
            created_at=row.created_at, updated_at=row.updated_at, finished_at=row.finished_at,
        )

    @staticmethod
    def _row_to_item(row: DailyRunItemRow) -> DailyRunItem:
        parsed = {f: _load_json(getattr(row, f)) for f in
                  ("sources_json", "fragments_json", "format_report_json",
                   "lint_warnings_json", "notes_json")}
        hashes = _load_json(row.source_hashes_json) or {}
        return DailyRunItem(
            date=row.date, target_path=row.target_path,
            # 计划生成时目标文件已存在（有 hash）→ 当天原本就有 A 类主骨架
            has_standard=bool(hashes.get(row.target_path)),
            sources=[DailySourceInfo(**s) for s in (parsed["sources_json"] or [])],
            fragments_to_delete=parsed["fragments_json"] or [],
            output_content=row.output_content, unified_diff=row.unified_diff,
            html_diff=render_html_diff(row.unified_diff) if row.unified_diff else None,
            format_report=FormatReport(**parsed["format_report_json"]) if parsed["format_report_json"]
            else FormatReport(ok=False),
            lint_warnings=[LintWarning(**w) for w in (parsed["lint_warnings_json"] or [])],
            notes=parsed["notes_json"] or [],
            empty_reason=row.empty_reason,
            decision=row.decision, status=row.item_status, error=row.error,
            backup_id=row.backup_id, applied_at=row.applied_at,
            prompt_tokens=row.prompt_tokens, completion_tokens=row.completion_tokens,
            total_tokens=row.total_tokens, cost_estimate_usd=row.cost_estimate_usd,
        )

    def _row_to_detail(self, row: DailyRunRow, items: list[DailyRunItemRow]) -> DailyRun:
        return DailyRun(
            **self._row_to_summary(row).model_dump(),
            extra_instructions=row.extra_instructions,
            items=[self._row_to_item(i) for i in items],
        )

    def _get_row(self, session, run_id: str) -> DailyRunRow:
        row = session.get(DailyRunRow, run_id)
        if row is None:
            raise DailyRunNotFoundError(f"批次不存在：{run_id}", details={"run_id": run_id})
        return row

    @staticmethod
    def _items_of(session, run_id: str) -> list[DailyRunItemRow]:
        return (session.query(DailyRunItemRow)
                .filter(DailyRunItemRow.run_id == run_id)
                .order_by(DailyRunItemRow.date).all())

    @staticmethod
    def _fragments_of(item: DailyRunItemRow) -> list[str]:
        """该日拟清理的碎片路径（B/C 类；A 类主文件 `YYYY-MM-DD.md` 不在此列）。"""
        return _load_json(item.fragments_json) or []

    def list(self, agent_id: str | None = None, status: str | None = None,
             limit: int = 50) -> list[DailyRunSummary]:
        with self.db.session() as s:
            q = s.query(DailyRunRow)
            if agent_id:
                q = q.filter(DailyRunRow.agent_id == agent_id)
            if status:
                q = q.filter(DailyRunRow.status == status)
            rows = q.order_by(DailyRunRow.created_at.desc()).limit(limit).all()
            return [self._row_to_summary(r) for r in rows]

    def get(self, run_id: str) -> DailyRun:
        with self.db.session() as s:
            return self._row_to_detail(self._get_row(s, run_id), self._items_of(s, run_id))

    # ---------- 创建 ----------

    @staticmethod
    def _validate_date(label: str, value: str) -> str:
        """日期参数校验：路径穿越 → 403；非法日期 → 400。

        目标路径恒为 `memory/<date>.md`（不由用户拼接），但日期会进文件名，
        所以这里仍然显式拦住 `/`、`\\`、`..` 这类字符。
        """
        if not value or any(ch in value for ch in ("/", "\\")) or ".." in value:
            raise UnsafePathError(f"{label} 含非法路径字符：{value!r}", details={label: value})
        if classify_daily_filename(f"{value}.md") is None:
            raise BadRequestError(f"{label} 必须是合法的 YYYY-MM-DD 日期", details={label: value})
        return value

    def _day_payload(self, agent_id: str, group: DayGroup) -> dict:
        """扫描结果的落库载荷：来源哈希（乐观锁）+ 来源概览 + 拟删碎片。"""
        hashes: dict[str, str] = {}
        sources = []
        for source in group.sources:
            text = self.file_manager.read_text(agent_id, source.path)
            hashes[source.path] = sha256_text(text)
            sources.append({
                "path": source.path, "kind": source.kind, "raw_bytes": source.size_bytes,
                "clean_bytes": source.size_bytes, "removed_total": 0,
            })
        target = group.target_path
        hashes[target] = sha256_text(self.file_manager.read_text(agent_id, target)) \
            if group.has_standard else ""
        return {
            "date": group.date, "target_path": target, "hashes": hashes, "sources": sources,
            "fragments": [s.path for s in group.fragments],
        }

    @staticmethod
    def _idempotency_key(agent_id: str, date_from: str, date_to: str, preset_id: str,
                         provider_id: str, day_payloads: list[dict]) -> str:
        """批次键：与来源内容绑定——同范围同内容重复提交直接复用，不产生第二次 LLM 调用。"""
        parts = [agent_id, date_from, date_to, preset_id, provider_id]
        for day in day_payloads:
            parts.append(day["date"])
            for path in sorted(day["hashes"]):
                parts.append(f"{path}:{day['hashes'][path]}")
        return sha256_text("|".join(parts))

    async def create(self, payload: DailyRunCreate) -> DailyRunCreateResult:
        """创建批次（异步执行）：校验 → 幂等复用 → 落库 → 后台逐日生成计划。"""
        agent_id = payload.agent_id
        self.file_manager.require_agent(agent_id)
        date_from = self._validate_date("date_from", payload.date_from)
        date_to = self._validate_date("date_to", payload.date_to)
        if date_from > date_to:
            raise BadRequestError("date_from 不能晚于 date_to",
                                  details={"date_from": date_from, "date_to": date_to})
        preset = self.presets.get(payload.preset_id)          # 不存在 → 404
        self.llm.get_provider(payload.provider_id)            # 不存在/禁用 → 404

        # 只处理「需要整理」的日子：同日多来源，或唯一来源质量差（方案坑 1：不能只看文件数）
        days = [g for g in self.scanner.scan_range(agent_id, date_from, date_to) if g.needs_rework]
        cfg = self.config.daily_standardizer
        if len(days) > cfg.max_days_per_run:
            raise BadRequestError(
                f"该范围有 {len(days)} 天需要整理，超过单批上限 {cfg.max_days_per_run} 天，请缩小范围",
                details={"days": len(days), "max_days_per_run": cfg.max_days_per_run})

        now = int(time.time())
        day_payloads = [self._day_payload(agent_id, g) for g in days]
        key = self._idempotency_key(agent_id, date_from, date_to, preset.id, payload.provider_id, day_payloads)
        with self.db.session() as s:
            existing = (s.query(DailyRunRow)
                        .filter(DailyRunRow.idempotency_key == key)
                        .order_by(DailyRunRow.created_at.desc()).first())
            if existing is not None and existing.status not in _TERMINAL_RUNS:
                return DailyRunCreateResult(
                    run_id=existing.id, status=existing.status, days_total=existing.days_total,
                    reused=True, created_at=existing.created_at)

            run_id = f"run-{uuid.uuid4().hex}"
            status = RUN_PLANNED if days else RUN_EMPTY
            s.add(DailyRunRow(
                id=run_id, agent_id=agent_id, date_from=date_from, date_to=date_to,
                preset_id=preset.id, preset_version=preset.version, provider_id=payload.provider_id,
                status=status, idempotency_key=key, extra_instructions=payload.extra_instructions,
                days_total=len(days), token_budget=cfg.token_budget,
                error=None if days else "该日期范围内没有需要整理的日子（无同日多来源，且无质量差的单来源）",
                created_at=now, updated_at=now, finished_at=None if days else now,
            ))
            for day in day_payloads:
                s.add(DailyRunItemRow(
                    run_id=run_id, date=day["date"], target_path=day["target_path"],
                    source_hashes_json=json.dumps(day["hashes"], ensure_ascii=False),
                    sources_json=json.dumps(day["sources"], ensure_ascii=False),
                    fragments_json=json.dumps(day["fragments"], ensure_ascii=False),
                    decision="pending", item_status=ITEM_PENDING, created_at=now, updated_at=now,
                ))
            s.commit()

        self.audit.record("daily_run_create", agent_id, None, {
            "run_id": run_id, "days": len(days), "date_from": date_from, "date_to": date_to,
            "preset_id": preset.id, "preset_version": preset.version, "provider_id": payload.provider_id,
            "token_budget": cfg.token_budget,
        })
        if days:
            asyncio.create_task(self.execute(run_id))
        return DailyRunCreateResult(run_id=run_id, status=status, days_total=len(days),
                                    reused=False, created_at=now)

    # ---------- 生成（后台） ----------

    def _update_item(self, run_id: str, date: str, **fields) -> None:
        with self.db.session() as s:
            row = (s.query(DailyRunItemRow)
                   .filter(DailyRunItemRow.run_id == run_id, DailyRunItemRow.date == date).first())
            if row is None:
                return
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = int(time.time())
            s.commit()

    def _save_item_plan(self, run_id: str, plan: DailyMergePlan, status: str,
                        error: str | None) -> None:
        self._update_item(
            run_id, plan.date, item_status=status, error=error,
            output_content=plan.output_content, unified_diff=plan.unified_diff,
            sources_json=json.dumps(
                [{"path": s.path, "kind": s.kind, "raw_bytes": s.raw_bytes,
                  "clean_bytes": s.clean_bytes, "removed_total": s.removed_total,
                  "summarized": s.summarized, "chunks": s.chunks} for s in plan.sources],
                ensure_ascii=False),
            fragments_json=json.dumps(plan.fragments_to_delete, ensure_ascii=False),
            format_report_json=json.dumps(plan.format_report.model_dump(), ensure_ascii=False),
            lint_warnings_json=json.dumps([w.model_dump() for w in plan.lint_warnings], ensure_ascii=False),
            notes_json=json.dumps(plan.notes, ensure_ascii=False),
            empty_reason=plan.empty_reason,
            prompt_tokens=plan.prompt_tokens, completion_tokens=plan.completion_tokens,
            total_tokens=plan.total_tokens, cost_estimate_usd=plan.cost_estimate_usd,
        )

    async def execute(self, run_id: str) -> None:
        """后台逐日生成计划：单日失败不中断整批；token 预算越限即中止剩余日期。"""
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status != RUN_PLANNED:
                return
            agent_id, preset_id, provider_id = run.agent_id, run.preset_id, run.provider_id
            extra, budget = run.extra_instructions, run.token_budget
            dates = [i.date for i in self._items_of(s, run_id)]

        tokens_used, cost = 0, 0.0
        stopped: str | None = None
        for date in dates:
            try:
                plan = await self.merge.plan_day(agent_id, date, preset_id, provider_id, extra)
            except Exception as e:  # 单日失败（LLM 报错 / 来源超限）不拖垮整批
                logger.warning(f"批次 {run_id} 的第 {date} 天生成失败：{e}")
                self._update_item(run_id, date, item_status=ITEM_FAILED, error=str(e))
                continue
            tokens_used += plan.total_tokens
            cost += plan.cost_estimate_usd
            if plan.is_empty:
                # 模型判定本日无可归档内容：不是失败，也不产出日文件；
                # 有碎片的日子仍待确认（清碎片要人工过一眼），没有碎片的日子无需任何动作
                self._save_item_plan(run_id, plan, ITEM_EMPTY, None)
            else:
                ok = plan.format_ok
                self._save_item_plan(
                    run_id, plan, ITEM_PLANNED if ok else ITEM_FAILED,
                    None if ok else "强规则校验未通过（章节缺失/顺序错误/禁项），该日不写入")
            if budget and tokens_used > budget:
                # 预算越限：不再发起任何 LLM 调用，剩余日期一律标 failed。
                # 已生成的计划**保留可确认**——写入本来就要人工逐个确认，因此不违反
                # 「越限不写入任何文件」；这里不浪费已经付过费的 token。
                stopped = (f"超出单批 token 预算（已用 {tokens_used} > 预算 {budget}），"
                           "已中止剩余日期且未写入任何文件")
                break

        if stopped:
            with self.db.session() as s:
                pending_dates = [i.date for i in
                                 (s.query(DailyRunItemRow)
                                  .filter(DailyRunItemRow.run_id == run_id,
                                          DailyRunItemRow.item_status == ITEM_PENDING).all())]
            for date in pending_dates:
                self._update_item(run_id, date, item_status=ITEM_FAILED, error=stopped)

        with self.db.session() as s:
            run = self._get_row(s, run_id)
            items = self._items_of(s, run_id)
            has_planned = any(i.item_status == ITEM_PLANNED for i in items)
            # 「无可归档内容」且仍有碎片待清的日子也是可执行的（确认后清碎片）
            has_cleanup = any(i.item_status == ITEM_EMPTY and self._fragments_of(i) for i in items)
            has_empty = any(i.item_status == ITEM_EMPTY for i in items)
            run.tokens_used = tokens_used
            run.cost_estimate_usd = round(cost, 6)
            run.error = stopped or run.error
            if has_planned or has_cleanup:
                run.status = RUN_AWAITING
            elif has_empty:
                # 全部判定无可归档内容且没有碎片要清：本批没有需要写入的文件
                run.status = RUN_EMPTY
                run.finished_at = int(time.time())
            else:
                run.status = RUN_FAILED
            run.updated_at = int(time.time())
            s.commit()
        logger.info(f"批次 {run_id} 计划生成完成：{len(dates)} 天，{tokens_used} tokens")

    # ---------- 确认 / 执行 ----------

    def reject(self, run_id: str) -> DailyRun:
        """拒绝批次（不写入任何文件）：未生成完的日期一并作废。"""
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status in (RUN_APPLIED, RUN_PARTIAL, RUN_REJECTED):
                raise DailyRunStatusError(f"批次已是终态（{run.status}），无需拒绝",
                                          details={"run_id": run_id, "status": run.status})
            for item in self._items_of(s, run_id):
                if item.item_status in (ITEM_PENDING, ITEM_PLANNED):
                    item.item_status = ITEM_SKIPPED
                    item.decision = "skipped"
            run.status = RUN_REJECTED
            run.finished_at = int(time.time())
            run.updated_at = int(time.time())
            s.commit()
        self.audit.record("daily_run_reject", None, None, {"run_id": run_id})
        return self.get(run_id)

    def skip(self, run_id: str, dates: list[str]) -> DailyRun:
        """跳过若干日（人工决策，不改写这些日）。"""
        wanted = {self._validate_date("date", d) for d in dates}
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status not in (RUN_AWAITING, RUN_PLANNED):
                raise DailyRunStatusError(
                    f"仅 awaiting_confirm / planned 状态可跳过某日，当前为 {run.status}",
                    details={"run_id": run_id, "status": run.status})
            items = self._items_of(s, run_id)
            hit = 0
            for item in items:
                if item.date in wanted and item.item_status in (ITEM_PENDING, ITEM_PLANNED, ITEM_EMPTY):
                    item.item_status = ITEM_SKIPPED
                    item.decision = "skipped"
                    hit += 1
            if hit == 0:
                raise BadRequestError("所选日期没有可跳过的条目（可能已应用/已跳过/不存在）",
                                      details={"dates": sorted(wanted)})
            run.status = self._final_status(items)
            run.updated_at = int(time.time())
            s.commit()
        self.audit.record("daily_run_skip", None, None, {"run_id": run_id, "dates": sorted(wanted)})
        return self.get(run_id)

    @staticmethod
    def _final_status(items: list[DailyRunItemRow]) -> str:
        """按逐日结果推导批次状态。

        优先级：还有未完成 → 等确认；有问题（生成失败 / 写前验收不过 / 空日碎片清理失败）
        → 需人工复核；碎片删失败 → 部分成功；有交付 → applied；
        全部为「无可归档内容」→ empty（本批没有需要写入的文件）；其余（全被跳过）→ rejected。
        """
        if any(i.item_status in (ITEM_PENDING, ITEM_PLANNED) for i in items):
            return RUN_AWAITING
        if any(i.item_status in (ITEM_FAILED, ITEM_BLOCKED) for i in items) or any(
                i.item_status == ITEM_EMPTY and i.error for i in items):
            return RUN_NEEDS_REVIEW
        if any(i.item_status == ITEM_PARTIAL for i in items):
            return RUN_PARTIAL
        if any(i.item_status == ITEM_APPLIED for i in items):
            return RUN_APPLIED
        if any(i.item_status == ITEM_EMPTY for i in items):
            return RUN_EMPTY
        return RUN_REJECTED

    @staticmethod
    def _acceptance_error(plan_output: str, rules) -> str | None:
        """写前验收：强规则 ok 且低价值元数据壳（M01~M10）残留 = 0。返回错误说明，None = 通过。"""
        report = FormatValidator().validate(plan_output, rules)
        if not report.ok:
            first = report.violations[0]
            return (f"强规则未通过（{len(report.violations)} 项，如 {first.rule_id} 第 {first.line} 行："
                    f"{first.message}）")
        residue = detect_residual_shells(plan_output)
        if residue:
            return f"仍残留低价值元数据壳：{describe_shells(residue)}"
        return None

    def _lock_conflict(self, agent_id: str, item: DailyRunItemRow) -> str | None:
        """乐观锁：目标文件当前内容必须与计划生成时一致。返回冲突说明，None = 一致。"""
        expected = (_load_json(item.source_hashes_json) or {}).get(item.target_path, "")
        try:
            actual = sha256_text(self.file_manager.read_text(agent_id, item.target_path))
        except Exception:  # 文件不存在 → 期望「不存在」才一致
            actual = ""
        if actual == expected:
            return None
        if expected and not actual:
            return f"{item.target_path} 已被外部删除（计划基于其旧内容）"
        if not expected:
            return f"{item.target_path} 已被外部创建（计划本要新建它）"
        return f"{item.target_path} 已被外部修改（计划基于旧版本）"

    def _fragment_conflicts(self, agent_id: str, item: DailyRunItemRow) -> list[str]:
        """空日清碎片前的乐观锁：逐个碎片比对计划生成时的 SHA-256（空日不写目标文件）。"""
        hashes = _load_json(item.source_hashes_json) or {}
        problems: list[str] = []
        for fragment in self._fragments_of(item):
            if fragment not in hashes:
                problems.append(f"{fragment}：计划中没有它的哈希，本次不删除")
                continue
            try:
                actual = sha256_text(self.file_manager.read_text(agent_id, fragment))
            except Exception:  # 文件不存在
                actual = ""
            if actual != hashes[fragment]:
                problems.append(f"{fragment}：已被外部删除或修改（计划基于旧内容）")
        return problems

    def _delete_fragments(self, agent_id: str, item: DailyRunItemRow) -> list[str]:
        """删除该日拟清理的碎片（走回收站）；返回失败说明（空 = 全部成功）。"""
        errors: list[str] = []
        for fragment in self._fragments_of(item):
            try:
                self.file_manager.delete(agent_id, fragment)
            except Exception as e:  # 碎片删失败 → 不写/不回滚日文件（方案 §7.3）
                errors.append(f"{fragment}：{e}")
        return errors

    @staticmethod
    def _actionable(item: DailyRunItemRow) -> bool:
        """该日是否有可执行动作：写入新内容，或（空日）清理碎片。"""
        if item.item_status == ITEM_PLANNED:
            return True
        return item.item_status == ITEM_EMPTY and bool(_load_json(item.fragments_json) or [])

    def apply(self, run_id: str, payload: DailyRunApplyRequest) -> DailyRunApplyResult:
        """应用选中的日期：批次级预检（乐观锁 + 写前验收）→ 写入 + 备份 + 删碎片 → 验收。

        「无可归档内容」的日期不写日文件，只清碎片（A 类主文件保持不动），
        预检改为逐个碎片比对哈希。
        """
        if self.config.daily_standardizer.dry_run_only:
            raise DailyRunDisabledError(
                "执行已被全局开关关闭（config.toml 的 daily_standardizer.dry_run_only=true），当前只能出计划",
                details={"run_id": run_id})

        with self.db.session() as s:
            run = self._get_row(s, run_id)
            if run.status != RUN_AWAITING:
                raise DailyRunStatusError(
                    f"仅 awaiting_confirm 状态可应用，当前为 {run.status}",
                    details={"run_id": run_id, "status": run.status})
            agent_id, preset_id = run.agent_id, run.preset_id
            items = self._items_of(s, run_id)
        rules = self.presets.rules_for(self.presets.get(preset_id))

        wanted = {self._validate_date("date", d) for d in payload.dates}
        targets = [i for i in items
                   if self._actionable(i) and (payload.apply_all or i.date in wanted)]
        if not targets:
            raise BadRequestError("没有可应用的日子（请选择日期，或确认该批次已有生成的计划）",
                                  details={"run_id": run_id, "dates": sorted(wanted)})

        # ① 批次级预检：有任何一个目标日不过 → 整批不写（零污染 + 并发保护）
        blocked: list[tuple[DailyRunItemRow, str]] = []
        conflicts: list[tuple[DailyRunItemRow, str]] = []
        for item in targets:
            if item.item_status == ITEM_EMPTY:  # 空日：只清碎片，锁在碎片上
                fragment_problems = self._fragment_conflicts(agent_id, item)
                if fragment_problems:
                    conflicts.append((item, "；".join(fragment_problems)))
                continue
            if not item.output_content:
                blocked.append((item, "该日没有生成内容（计划缺失）"))
                continue
            problem = self._acceptance_error(item.output_content, rules)
            if problem:
                blocked.append((item, problem))
                continue
            conflict = self._lock_conflict(agent_id, item)
            if conflict:
                conflicts.append((item, conflict))
        if conflicts:
            details = [{"date": item.date, "reason": reason} for item, reason in conflicts]
            for item, reason in conflicts:
                self._update_item(run_id, item.date, item_status=ITEM_FAILED, error=reason)
            raise ConflictError(
                f"有 {len(conflicts)} 天的目标文件或碎片已被外部改动，本次未写入任何文件；请重新生成计划",
                details={"conflicts": details})
        for item, reason in blocked:
            self._update_item(run_id, item.date, item_status=ITEM_BLOCKED, error=reason)
            self.audit.record("daily_run_blocked", agent_id, item.target_path,
                              {"run_id": run_id, "date": item.date, "reason": reason}, result="failed")

        # ② 逐个写入 + 删碎片（被 blocked 的日期不写；空日只删碎片）
        applied: list[str] = []
        partial: list[str] = []
        failed: list[str] = []
        no_content: list[str] = []
        blocked_dates = {item.date for item, _ in blocked}
        now = int(time.time())
        for item in targets:
            if item.date in blocked_dates:
                continue
            if item.item_status == ITEM_EMPTY:
                cleanup_errors = self._delete_fragments(agent_id, item)
                self._update_item(
                    run_id, item.date, item_status=ITEM_EMPTY, decision="applied",
                    applied_at=now, backup_id=None,
                    error=(f"碎片删除失败（本日未产出日文件，可手工清理）：{'；'.join(cleanup_errors)}"
                           if cleanup_errors else None))
                no_content.append(item.date)
                self.audit.record("daily_empty_content", agent_id, item.target_path, {
                    "run_id": run_id, "date": item.date, "reason": item.empty_reason,
                    "fragments_deleted": len(self._fragments_of(item)) - len(cleanup_errors),
                    "fragments_failed": cleanup_errors, "tokens": item.total_tokens,
                    "cost_estimate_usd": item.cost_estimate_usd,
                }, result="failed" if cleanup_errors else "ok")
                continue
            try:
                result = self.file_manager.write(
                    agent_id, item.target_path, item.output_content or "",
                    reason="daily-standardize", audit=False)
            except Exception as e:
                logger.warning(f"批次 {run_id} 写 {item.target_path} 失败：{e}")
                self._update_item(run_id, item.date, item_status=ITEM_FAILED, error=str(e))
                failed.append(item.date)
                continue

            cleanup_errors = self._delete_fragments(agent_id, item)
            item_status = ITEM_PARTIAL if cleanup_errors else ITEM_APPLIED
            error = ("碎片删除失败（日文件已保留，可手工清理）：" + "；".join(cleanup_errors)) \
                if cleanup_errors else None
            self._update_item(run_id, item.date, item_status=item_status, decision="applied",
                              applied_at=now, backup_id=result.backup_id, error=error)
            (partial if cleanup_errors else applied).append(item.date)
            self.audit.record("daily_apply", agent_id, item.target_path, {
                "run_id": run_id, "date": item.date, "backup_id": result.backup_id,
                "fragments_deleted": len(self._fragments_of(item)) - len(cleanup_errors),
                "fragments_failed": cleanup_errors, "tokens": item.total_tokens,
                "cost_estimate_usd": item.cost_estimate_usd,
            }, result="failed" if cleanup_errors else "ok")

        # ③ 收尾：写状态 + 跑验收（不通过则 needs_review）
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            items = self._items_of(s, run_id)
            status = self._final_status(items)
            run.status = status
            run.updated_at = int(time.time())
            if status in (RUN_APPLIED, RUN_PARTIAL, RUN_NEEDS_REVIEW, RUN_REJECTED, RUN_EMPTY):
                run.finished_at = int(time.time())
            s.commit()
        report = self.build_report(run_id)
        if not report.passed:
            with self.db.session() as s:
                run = self._get_row(s, run_id)
                if run.status != RUN_PARTIAL:
                    run.status = RUN_NEEDS_REVIEW
                run.updated_at = int(time.time())
                s.commit()
        final = self.get(run_id)
        return DailyRunApplyResult(
            run_id=run_id, status=final.status, applied=applied, partial=partial,
            blocked=[item.date for item, _ in blocked], failed=failed,
            no_content=no_content,
            skipped=[i.date for i in final.items if i.status == ITEM_SKIPPED],
        )

    # ---------- 验收报告 ----------

    def build_report(self, run_id: str) -> DailyRunReport:
        """对手写盘后的**真实文件**做验收核对（方案 §9.2 的 1/2/3/4/7 条）。

        只读：不改批次状态（状态由 `apply()` 决定），因此随时可重复跑。
        """
        with self.db.session() as s:
            run = self._get_row(s, run_id)
            items = self._items_of(s, run_id)
        agent_id, preset_id = run.agent_id, run.preset_id
        rules = self.presets.rules_for(self.presets.get(preset_id))
        validator = FormatValidator()
        workspace = Path(self.file_manager.require_agent(agent_id).workspace)

        entries: list[DailyRunReportItem] = []
        for item in items:
            entry = DailyRunReportItem(
                date=item.date, target_path=item.target_path, status=item.item_status,
                empty=item.item_status == ITEM_EMPTY,
                delivered=item.item_status in (ITEM_APPLIED, ITEM_PARTIAL),
            )
            if entry.empty:
                # 判定「无可归档内容」的日期：不产出日文件（章节/命名/单文件三项不适用），
                # 只核对 B/C 碎片是否已清；A 类主文件本来就该原地不动
                state = "" if item.decision == "applied" else "（尚未处理）"
                entry.details.append(
                    f"判定无可归档内容{state}：{item.empty_reason or '（模型未给理由）'}")
                leftovers = [p for p in self._fragments_of(item) if (workspace / p).exists()]
                entry.fragments_gone = not leftovers
                if leftovers:
                    entry.details.append("碎片未清理：" + "、".join(leftovers))
                if item.error:
                    entry.details.append(item.error)
                entries.append(entry)
                continue
            if not entry.delivered:
                entry.details.append(item.error or f"未交付（{item.item_status}）")
                entries.append(entry)
                continue

            entry.naming_ok = item.target_path == f"memory/{item.date}.md"
            if not entry.naming_ok:
                entry.details.append(f"命名不合规：{item.target_path}")

            try:
                content = self.file_manager.read_text(agent_id, item.target_path)
            except Exception as e:
                entry.sections_ok = entry.no_residue = False
                entry.details.append(f"目标文件读不到：{e}")
                entries.append(entry)
                continue

            report = validator.validate(content, rules)
            entry.sections_ok = report.ok
            if not report.ok:
                entry.details.append(
                    "章节校验未通过：" + "；".join(f"{v.rule_id}(第 {v.line} 行) {v.message}"
                                                  for v in report.violations[:3]))
            residue = detect_residual_shells(content)
            entry.no_residue = not residue
            if residue:
                entry.details.append(f"仍有低价值元数据壳：{describe_shells(residue)}")

            leftovers = [p for p in (_load_json(item.fragments_json) or [])
                         if (workspace / p).exists()]
            entry.fragments_gone = not leftovers
            if leftovers:
                entry.details.append("碎片未清理：" + "、".join(leftovers))

            remaining = _day_files(workspace, item.date)
            entry.single_file = remaining == [item.target_path]
            if not entry.single_file:
                entry.details.append("同一天仍存在多个文件：" + "、".join(remaining))
            entries.append(entry)

        delivered = [e for e in entries if e.delivered]
        # 空日只核对「碎片已清」（其余四项不适用）
        emptied = [e for e in entries if e.empty]
        problems = [e for e in entries if e.status in (ITEM_FAILED, ITEM_BLOCKED)]
        passed = (
            not problems
            and all(e.single_file and e.naming_ok and e.sections_ok and e.no_residue
                    and e.fragments_gone for e in delivered)
            and all(e.fragments_gone for e in emptied)
        )
        return DailyRunReport(
            run_id=run_id, agent_id=agent_id, status=run.status, passed=passed, items=entries,
            days_delivered=len(delivered), days_total=run.days_total,
            tokens_used=run.tokens_used, cost_estimate_usd=run.cost_estimate_usd,
            generated_at=int(time.time()),
        )


def _load_json(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _day_files(workspace: Path, date: str) -> list[str]:
    """`memory/` 顶层属于该日期的文件（Agent 相对路径，用于核对「每天恰好 1 个文件」）。"""
    memory = workspace / "memory"
    if not memory.is_dir():
        return []
    return sorted(
        p.relative_to(workspace).as_posix() for p in memory.glob("*.md")
        if (classify_daily_filename(p.name) or (None, None))[1] == date)
