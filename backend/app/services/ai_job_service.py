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
from app.services.format_validator import FormatValidator, FormatReport
from app.services.lint_service import LintService
from app.services.llm_registry import LLMRegistry
from app.services.preset_service import PresetService
from app.services.template_rules import RequiredSection, TemplateRules, parse_template, template_rule_summary

AI_FILE_SIZE_LIMIT = 30 * 1024  # 30KB（token 成本 + 质量风险）

SYSTEM_PROMPT = (
    "你是 Soulforge 的 AI 文档整理助手。"
    "严格遵守用户给出的「格式化规则」重新整理目标文档：保留原意、不丢失信息、不新增事实。"
    "输出必须 100% 符合规则，正文只输出 Markdown 内容。"
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
        """解析预设模板规则；无模板文档时由 sections 兜底构造。"""
        if preset.template_md:
            return parse_template(preset.template_md)
        return TemplateRules(
            name=preset.name, target_file_type=preset.target_file_type,
            required_sections=[
                RequiredSection(title=sec.title, required=sec.required)
                for sec in sorted(preset.sections_json, key=lambda x: x.order)
            ],
        )

    @staticmethod
    def _build_prompt(preset: Preset, content: str, extra_instructions: str | None) -> str:
        rules = AIJobService._rules_for(preset)
        summary = template_rule_summary(rules)
        skeleton = preset.template_md or "（该预设未提供模板文档，以上规则即全部要求）"
        return f"""【任务】按下方「格式化规则」对目标文档做结构化重排与格式校验，严格遵循：
第一步：读取并解析格式化规则；
第二步：加载目标文档；
第三步：按照全部格式化规则对目标文档进行结构化重新整理（保留原意，不丢失、不新增信息）；
第四步：自查输出，确保 100% 符合规则后再交付。

【格式化规则（来自模板文档，必须逐条遵守）】
{summary}

【模板文档全文（含章节骨架示例，重排时按此结构组织）】
```markdown
{skeleton}
```

【附加指令】（老板可选）
{extra_instructions or '无'}

【目标文档】
```markdown
{content}
```

【输出】只输出整理后的 Markdown 内容，不要解释，不要任何前缀。"""

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
            # 第四步：按模板规则做格式校验 + 机械性自动修正，产出最终输出
            output, format_report = FormatValidator().validate_and_fix(raw_output, rules)
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

    def apply(self, job_id: str) -> AIJobApplyResult:
        """老板点应用：格式校验 + lint 拦截 → 备份原文件 → 写入 → applied + 审计。"""
        with self.db.session() as s:
            row = self._get_row(s, job_id)
            if row.status != "awaiting_confirm":
                raise AIJobStatusError(
                    f"仅 awaiting_confirm 状态可应用，当前为 {row.status}",
                    details={"job_id": job_id, "status": row.status})
            output = row.output_content or ""
            agent_id, file_path, provider_id = row.agent_id, row.file_path, row.provider_id
            diff_plan_json = row.diff_plan_json

        # 输出必须 100% 符合模板格式规范，否则拒绝写入
        try:
            diff_plan = AIJobDiffPlan(**json.loads(diff_plan_json or "{}"))
        except (json.JSONDecodeError, TypeError):
            diff_plan = None
        if diff_plan is not None and not diff_plan.format_report.ok:
            with self.db.session() as s:
                row = self._get_row(s, job_id)
                row.status = "failed"
                row.error = "AI 输出未通过模板格式校验，拒绝写入"
                row.finished_at = int(time.time())
                row.updated_at = int(time.time())
                s.commit()
            raise FormatViolationError(
                "AI 输出未通过模板格式校验，拒绝写入",
                details={"job_id": job_id, "violations": [v.model_dump() for v in diff_plan.format_report.violations]})

        # 输出过 lint，违规拒绝写入
        warnings = self.lint.lint_file(agent_id, file_path, output)
        if warnings:
            with self.db.session() as s:
                row = self._get_row(s, job_id)
                row.status = "failed"
                row.error = "AI 输出未通过 lint 检查，拒绝写入"
                row.finished_at = int(time.time())
                row.updated_at = int(time.time())
                s.commit()
            raise AILintBlockedError(
                "AI 输出未通过 lint 检查，拒绝写入", details={"job_id": job_id, "warnings": [w.model_dump() for w in warnings]})

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
            "total_tokens": row.total_tokens, "cost_estimate_usd": row.cost_estimate_usd,
        })
        return AIJobApplyResult(job_id=job_id, status="applied", backup_id=backup_id, file_size=result.size_bytes)

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
