"""AIJobService（M13 · AI 自动整理，Phase 2.5 Step 3）。

流程：老板选文件+预设+provider → create(pending) → 后台异步 execute
→ awaiting_confirm → 老板 apply/reject/regenerate。

护栏：
- AI 输出绝不直接覆盖原文件，必须经老板 diff 确认
- 大文件（> 30KB）拒绝 AI 整理
- apply 时 AI 输出必须过 lint，违规拒绝写入
- 单文件单次 AI 调用（不自动循环）
- 每次调用记录 provider + token 消耗 + 成本（审计日志）
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from loguru import logger

from app.core.errors import (
    AIFileTooLargeError,
    AIJobNotFoundError,
    AIJobStatusError,
    AILintBlockedError,
    FileNotFoundError,
    FormatViolationError,
)
from app.core.security import _safe_join
from app.models.db import AIJobRow, Database
from app.models.schemas import (
    AIJob,
    AIJobApplyResult,
    AIJobCreateResult,
    AIJobDiffPlan,
    AIJobSummary,
    Preset,
)
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.diff_service import unified_diff
from app.services.file_manager import FileManager
from app.services.format_validator import FormatValidator
from app.services.lint_service import LintService
from app.services.llm_registry import LLMRegistry
from app.services.preset_service import PresetService
from app.services.template_rules import (
    RequiredSection,
    TemplateRules,
    apply_format_rules,
    parse_preset,
    template_body,
)

AI_FILE_SIZE_LIMIT = 30 * 1024  # 30KB（token 成本 + 质量风险）

SYSTEM_PROMPT = (
    "你是 Soulforge 的 AI 文档整理助手。"
    "严格依据「预设参考文档」与「修改要求」两项配置修改目标文档：保留原意、不丢失信息、不新增事实。"
    "输出必须完全符合这两项配置，正文只输出 Markdown 内容。"
    "不要输出任何思考过程、任务分析、配置复述或对话性文字（如「让我…」「以下是…」），"
    "第一行就要直接进入文档正文。"
)


class AIJobService:
    """AI 整理任务生命周期管理（后台执行基于 asyncio.create_task）。"""

    def __init__(self, db: Database, file_manager: FileManager, backup: BackupService,
                 lint: LintService, audit: AuditService, presets: PresetService, llm: LLMRegistry):
        self.db = db
        self.file_manager = file_manager
        self.backup = backup
        self.lint = lint
        self.audit = audit
        self.presets = presets
        self.llm = llm

    # ---------- 查询 ----------

    def _row_to_summary(self, row: AIJobRow) -> AIJobSummary:
        return AIJobSummary(
            id=row.id, agent_id=row.agent_id, file_path=row.file_path,
            preset_id=row.preset_id, provider_id=row.provider_id, status=row.status,
            created_at=row.created_at, updated_at=row.updated_at,
            finished_at=row.finished_at, superseded_by=row.superseded_by,
        )

    def _row_to_detail(self, row: AIJobRow) -> AIJob:
        diff_plan = None
        if row.diff_plan_json:
            try:
                diff_plan = AIJobDiffPlan(**json.loads(row.diff_plan_json))
            except (json.JSONDecodeError, TypeError):
                diff_plan = None
        return AIJob(
            **self._row_to_summary(row).model_dump(),
            input_snapshot=row.input_snapshot, output_content=row.output_content,
            diff_plan_json=diff_plan, extra_instructions=row.extra_instructions,
            prompt_tokens=row.prompt_tokens, completion_tokens=row.completion_tokens,
            total_tokens=row.total_tokens, cost_estimate_usd=row.cost_estimate_usd,
            error=row.error,
        )

    def _get_row(self, session, job_id: str) -> AIJobRow:
        row = session.get(AIJobRow, job_id)
        if row is None:
            raise AIJobNotFoundError(f"AI 任务不存在：{job_id}", details={"job_id": job_id})
        return row

    def get(self, job_id: str) -> AIJob:
        with self.db.session() as s:
            return self._row_to_detail(self._get_row(s, job_id))

    def list(self, agent_id: str | None = None, status: str | None = None, limit: int = 50) -> list[AIJobSummary]:
        with self.db.session() as s:
            q = s.query(AIJobRow)
            if agent_id:
                q = q.filter(AIJobRow.agent_id == agent_id)
            if status:
                q = q.filter(AIJobRow.status == status)
            rows = q.order_by(AIJobRow.created_at.desc()).limit(limit).all()
            return [self._row_to_summary(r) for r in rows]

    # ---------- 创建 / 后台执行 ----------

    def _validate_target(self, agent_id: str, file_path: str) -> None:
        """校验 Agent/文件存在且大小 ≤ 30KB。"""
        agent = self.file_manager.require_agent(agent_id)
        full = _safe_join(Path(agent.workspace), file_path)
        if not full.is_file():
            raise FileNotFoundError(f"{agent_id} workspace 下找不到 {file_path}",
                                    details={"agent_id": agent_id, "path": file_path})
        if full.stat().st_size > AI_FILE_SIZE_LIMIT:
            raise AIFileTooLargeError(
                f"文件 {full.stat().st_size // 1024}KB 超过 30KB，拒绝 AI 整理（token 成本 + 质量风险）",
                details={"file_path": file_path, "size_bytes": full.stat().st_size})

    async def create(self, agent_id: str, file_path: str, preset_id: str, provider_id: str,
                     extra_instructions: str | None = None) -> AIJobCreateResult:
        """创建任务（status=pending），提交后台队列执行。"""
        self._validate_target(agent_id, file_path)
        self.presets.get(preset_id)  # 不存在 → 404
        self.llm.get_provider(provider_id)  # 不存在/禁用 → 404
        now = int(time.time())
        job_id = f"job-{uuid.uuid4().hex}"
        with self.db.session() as s:
            s.add(AIJobRow(
                id=job_id, agent_id=agent_id, file_path=file_path,
                preset_id=preset_id, provider_id=provider_id,
                status="pending", extra_instructions=extra_instructions,
                created_at=now, updated_at=now,
            ))
            s.commit()
        asyncio.create_task(self.execute(job_id))
        return AIJobCreateResult(job_id=job_id, status="pending", created_at=now)

    def _set_status(self, job_id: str, status: str, *, error: str | None = None,
                    finished: bool = False) -> None:
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            row.status = status
            if error is not None:
                row.error = error
            if finished:
                row.finished_at = int(time.time())
            row.updated_at = int(time.time())
            s.commit()

    @staticmethod
    def _rules_for(preset: Preset) -> TemplateRules:
        """解析预设模板规则（参考文档 + 结构化规则）；无参考文档时由 sections 兜底构造。"""
        if preset.template_md:
            rules = parse_preset(preset.template_md, preset.format_rules)
        else:
            rules = TemplateRules(
                name=preset.name, target_file_type=preset.target_file_type,
                required_sections=[
                    RequiredSection(title=sec.title, required=sec.required)
                    for sec in sorted(preset.sections_json, key=lambda x: x.order)
                ],
            )
            apply_format_rules(rules, preset.format_rules)
        rules.target_file_type = preset.target_file_type
        return rules

    @staticmethod
    def _build_prompt(preset: Preset, content: str, extra_instructions: str | None) -> str:
        """组装文档修改任务的 prompt。

        **只以两项配置为核心参照依据**：
        - 「预设参考文档」（`preset.template_md`，纯 Markdown）—— 体现目标文档的结构与写法；
        - 「修改要求」（`preset.style_rules`，逐条）—— 明确要保留 / 删除 / 改写什么。
        不再注入任何机器规则摘要（章节 / 顺序等「章节」配置已移除）。
        """
        reference = template_body(preset.template_md) or "（该预设未提供参考文档）"
        requirement_block = (
            "\n".join(f"{i}. {line}" for i, line in enumerate(preset.style_rules, start=1))
            if preset.style_rules
            else "（无）"
        )
        return f"""【任务】严格依据下方「预设参考文档」与「修改要求」两项配置，修改目标文档：
第一步：阅读并理解「预设参考文档」与「修改要求」；
第二步：加载目标文档；
第三步：严格按「预设参考文档」所示的结构与写法、以及「修改要求」提出的每一条要求修改目标文档
        （保留原文意图，不丢失、不新增信息）；
第四步：自查输出，确认完全符合两项配置后再交付。

【预设参考文档】
```markdown
{reference}
```

【修改要求（必须逐条遵守）】
{requirement_block}

【附加指令】（可选）
{extra_instructions or '无'}

【目标文档】
```markdown
{content}
```

【输出】只输出修改后的 Markdown 文档正文本身，严格遵守：
1. 第一行必须是文档标题（ATX 标题，如 `# SOUL.md`）；约定要求 frontmatter 时，第一行必须是 `---`；
2. 禁止输出思考过程、任务分析、步骤说明、配置复述、前言/结语、致谢等任何对话性文字；
3. 禁止用 ``` 代码围栏包裹整篇文档（文档内部的代码块不受此限）；
4. 不要写「让我」「以下是」「以上是」「如需调整」之类的话，直接从正文开始、到正文结束。"""

    async def execute(self, job_id: str) -> None:
        """后台异步执行四步流程：
        1. 解析模板规则 → 2. 加载目标文档 → 3. AI 按规则重排 → 4. 格式校验+机械修正。
        修正后的输出必须 format_report.ok 才允许进入 awaiting_confirm。
        """
        try:
            self._set_status(job_id, "running")
            with self.db.session() as s:
                row = self._get_row(s, job_id)
                agent_id, file_path, preset_id, provider_id, extra = (
                    row.agent_id, row.file_path, row.preset_id, row.provider_id, row.extra_instructions)

            content = self.file_manager.read_text(agent_id, file_path)
            preset = self.presets.get(preset_id)
            rules = self._rules_for(preset)
            prompt = self._build_prompt(preset, content, extra)

            client = self.llm.get_client(provider_id)
            resp = await client.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            raw_output = resp.content.strip()
            # 前置净化：剥离模型的思考过程/前言，以及整篇文档的围栏包裹
            validator = FormatValidator()
            sanitized, preamble = validator.sanitize(raw_output)
            if preamble:
                logger.warning(f"AI 输出含前言，已在写入前剥离（job={job_id}）：{preamble[:120]!r}")
            # 第四步：按模板规则做格式校验 + 机械性自动修正，产出最终输出
            output, format_report = validator.validate_and_fix(sanitized, rules)
            diff = unified_diff(content, output, fromfile=f"{agent_id}/{file_path}", tofile="AI 整理后")
            warnings = self.lint.lint_file(agent_id, file_path, output)
            diff_plan = AIJobDiffPlan(
                unified_diff=diff, lint_warnings=warnings, format_report=format_report)

            with self.db.session() as s:
                row = self._get_row(s, job_id)
                row.status = "awaiting_confirm"
                row.input_snapshot = content
                row.output_content = output
                row.diff_plan_json = json.dumps(diff_plan.model_dump(), ensure_ascii=False)
                row.prompt_tokens = resp.usage.prompt_tokens
                row.completion_tokens = resp.usage.completion_tokens
                row.total_tokens = resp.usage.total_tokens
                row.cost_estimate_usd = resp.cost_estimate_usd
                row.updated_at = int(time.time())
                s.commit()
        except Exception as e:  # LLM 失败 / lint 异常等 → failed
            with self.db.session() as s:
                row = s.get(AIJobRow, job_id)
                if row is not None:
                    row.status = "failed"
                    row.error = str(e)
                    row.finished_at = int(time.time())
                    row.updated_at = int(time.time())
                    s.commit()

    # ---------- 确认动作 ----------

    def apply(self, job_id: str, content: str | None = None) -> AIJobApplyResult:
        """老板点应用：格式校验 + lint 拦截 → 备份原文件 → 写入 → applied + 审计。

        `content` 为空 → 写入 AI 完整输出（沿用 plan 生成时的格式校验结果）；
        非空 → 「按块接受」的重建内容，会按同一套模板规则重新做格式校验，
        lint 闸门对两条路径一致生效。任一闸门不通过都拒绝写入并标记任务失败。
        """
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            if row.status != "awaiting_confirm":
                raise AIJobStatusError(
                    f"仅 awaiting_confirm 状态可应用，当前为 {row.status}",
                    details={"job_id": job_id, "status": row.status})
            output = content if content is not None else (row.output_content or "")
            agent_id, file_path, provider_id = row.agent_id, row.file_path, row.provider_id
            preset_id = row.preset_id
            diff_plan_json = row.diff_plan_json
            total_tokens, cost_estimate_usd = row.total_tokens, row.cost_estimate_usd

        if content is None:
            # 完整输出：沿用 plan 生成时的格式校验结果
            try:
                diff_plan = AIJobDiffPlan(**json.loads(diff_plan_json or "{}"))
            except (json.JSONDecodeError, TypeError):
                diff_plan = None
            if diff_plan is not None and not diff_plan.format_report.ok:
                self._fail(job_id, "AI 输出未通过模板格式校验，拒绝写入")
                raise FormatViolationError(
                    "AI 输出未通过模板格式校验，拒绝写入",
                    details={"job_id": job_id,
                             "violations": [v.model_dump() for v in diff_plan.format_report.violations]})
        else:
            # 按块接受：对重建后的内容重新跑同一套模板格式校验
            rules = self._rules_for(self.presets.get(preset_id))
            _, format_report = FormatValidator().validate_and_fix(output, rules)
            if not format_report.ok:
                self._fail(job_id, "按块接受的输出未通过模板格式校验，拒绝写入")
                raise FormatViolationError(
                    "按块接受的输出未通过模板格式校验，拒绝写入",
                    details={"job_id": job_id,
                             "violations": [v.model_dump() for v in format_report.violations]})

        # 输出过 lint，违规拒绝写入
        warnings = self.lint.lint_file(agent_id, file_path, output)
        if warnings:
            self._fail(job_id, "AI 输出未通过 lint 检查，拒绝写入")
            raise AILintBlockedError(
                "AI 输出未通过 lint 检查，拒绝写入",
                details={"job_id": job_id, "warnings": [w.model_dump() for w in warnings]})

        agent = self.file_manager.require_agent(agent_id)
        full = _safe_join(Path(agent.workspace), file_path)
        backup_id = None
        if full.is_file():
            backup_id = self.backup.backup(agent_id, file_path, full, reason="pre-ai-apply")
        result = self.file_manager.write(agent_id, file_path, output, auto_backup=False, audit=False)

        with self.db.session() as s:
            row = self._get_row(s, job_id)
            row.status = "applied"
            row.finished_at = int(time.time())
            row.updated_at = int(time.time())
            s.commit()
        self.audit.record("ai_apply", agent_id, file_path, {
            "job_id": job_id, "backup_id": backup_id, "provider_id": provider_id,
            "total_tokens": total_tokens, "cost_estimate_usd": cost_estimate_usd,
            "partial": content is not None,
        })
        return AIJobApplyResult(job_id=job_id, status="applied", backup_id=backup_id, file_size=result.size_bytes)

    def _fail(self, job_id: str, error: str) -> None:
        """把任务标记为 failed（闸门拦截 / 应用失败时统一入口）。"""
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            row.status = "failed"
            row.error = error
            row.finished_at = int(time.time())
            row.updated_at = int(time.time())
            s.commit()

    def reject(self, job_id: str) -> AIJob:
        """老板点拒绝：不写入。"""
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            if row.status != "awaiting_confirm":
                raise AIJobStatusError(
                    f"仅 awaiting_confirm 状态可拒绝，当前为 {row.status}",
                    details={"job_id": job_id, "status": row.status})
            row.status = "rejected"
            row.finished_at = int(time.time())
            row.updated_at = int(time.time())
            s.commit()
            return self._row_to_detail(row)

    async def regenerate(self, job_id: str, extra_instructions: str) -> AIJobCreateResult:
        """老板点重新生成：旧 job 标记 superseded → 创建新 job（pending）→ 后台执行。"""
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            agent_id, file_path, preset_id, provider_id = (
                row.agent_id, row.file_path, row.preset_id, row.provider_id)
        new_result = await self.create(agent_id, file_path, preset_id, provider_id, extra_instructions)
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            row.status = "superseded"
            row.superseded_by = new_result.job_id
            row.finished_at = int(time.time())
            row.updated_at = int(time.time())
            s.commit()
        return new_result
