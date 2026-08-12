"""PresetService（M11 · 文档预设系统，Phase 2.5 Step 1）。

职责：
- 预设 CRUD（系统预设不可删、仅允许改 description + style_rules；version 自增）
- 内置预设播种（4 个，is_system=1）
- 应用预设：plan + execute 两步，plan 只读不写，execute 是唯一写入口
  （写前备份 + 审计，绝不直接覆盖）
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from app.core.errors import (
    BadRequestError,
    PresetNotFoundError,
    PresetPlanExpiredError,
    PresetPlanNotFoundError,
)
from app.core.security import _safe_join
from app.models.db import Database, PresetRow, PresetVersionRow
from app.models.schemas import (
    FormatReport,
    Preset,
    PresetApplyPlan,
    PresetApplyResult,
    PresetCreate,
    PresetSection,
    PresetSummary,
    PresetUpdate,
    PresetVersionInfo,
)
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.diff_service import unified_diff
from app.services.file_manager import FileManager
from app.services.format_validator import FormatValidator
from app.services.lint_service import LintService
from app.services.preset_templates import BUILTIN_TEMPLATES
from app.services.template_rules import RequiredSection, TemplateRules, derive_sections, parse_template

PLAN_TTL_SECONDS = 30 * 60  # apply plan ≤ 30 分钟有效（与 sync plan 一致）


def _parse_json(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default

# 内置预设（v1）：id 前缀 preset-，is_system=1，见 docs/ROADMAP.md 2.3
BUILTIN_PRESETS: list[dict] = [
    {
        "id": "preset-soul-std",
        "name": "SOUL 标准结构",
        "target_file_type": "SOUL",
        "description": "新建/重整 SOUL.md：核心行为准则、工作态度、学习连续性、核心边界",
        "sections": [
            {"title": "核心行为准则", "required": True, "order": 1, "hint": "简洁优先、目标导向"},
            {"title": "工作态度和原则", "required": True, "order": 2, "hint": "先想后做、不吹嘘"},
            {"title": "学习与连续性", "required": True, "order": 3, "hint": "记录、更新、演进"},
            {"title": "核心边界", "required": True, "order": 4, "hint": "隐私、操作授权"},
        ],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
        "style_rules": ["emoji-in-section-title=false", "口语化禁令", "必须带应用范例"],
    },
    {
        "id": "preset-agents-std",
        "name": "AGENTS 标准结构",
        "target_file_type": "AGENTS",
        "description": "新建/重整 AGENTS.md：启动流程、记忆、工具、群聊、安全",
        "sections": [
            {"title": "首次运行", "required": True, "order": 1, "hint": "初始化流程"},
            {"title": "启动流程", "required": True, "order": 2, "hint": "每次会话如何开始"},
            {"title": "记忆", "required": True, "order": 3, "hint": "记忆读写规则"},
            {"title": "工具", "required": True, "order": 4, "hint": "可用工具与使用边界"},
            {"title": "群聊", "required": True, "order": 5, "hint": "多 Agent 协作规则"},
            {"title": "安全", "required": True, "order": 6, "hint": "安全护栏与禁止项"},
        ],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
        "style_rules": ["emoji-in-section-title=false", "口语化禁令", "规则必须可执行"],
    },
    {
        "id": "preset-mem-std",
        "name": "MEMORY 标准结构",
        "target_file_type": "MEMORY",
        "description": "重整长期记忆：重要决定、经验教训、待办、执行摘要",
        "sections": [
            {"title": "重要决定", "required": True, "order": 1, "hint": "记录影响后续行为的决定"},
            {"title": "经验教训", "required": True, "order": 2, "hint": "踩坑与心得"},
            {"title": "待办事项", "required": True, "order": 3, "hint": "未完成事项"},
            {"title": "执行摘要", "required": True, "order": 4, "hint": "当前状态速览"},
        ],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
        "style_rules": ["事实优先、结论先行", "不写过程叙述", "必须带时间标注"],
    },
    {
        "id": "preset-wlog-summary",
        "name": "工作日志汇总",
        "target_file_type": "WORKLOG",
        "description": "整理 memory/YYYY-MM-DD.md：按时间倒序归档、提取关键决策",
        "sections": [
            {"title": "今日概览", "required": True, "order": 1, "hint": "当日核心成果"},
            {"title": "关键决策", "required": True, "order": 2, "hint": "值得长期记住的决定"},
            {"title": "待办与风险", "required": True, "order": 3, "hint": "未完成事项与隐患"},
            {"title": "明日计划", "required": True, "order": 4, "hint": "下一步安排"},
        ],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
        "style_rules": ["按时间倒序归档", "只提取关键决策，不保留流水账", "口语化禁令"],
    },
]


class PresetService:
    """文档预设：CRUD + 应用（plan + execute 两步）。"""

    def __init__(self, db: Database, file_manager: FileManager, backup: BackupService,
                 lint: LintService, audit: AuditService):
        self.db = db
        self.file_manager = file_manager
        self.backup = backup
        self.lint = lint
        self.audit = audit
        self._plans: dict[str, tuple[float, PresetApplyPlan]] = {}

    # ---------- 辅助 ----------

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [pid for pid, (ts, _) in self._plans.items() if now - ts > PLAN_TTL_SECONDS]
        for pid in expired:
            self._plans.pop(pid, None)

    @staticmethod
    def _row_to_summary(row: PresetRow) -> PresetSummary:
        return PresetSummary(
            id=row.id, name=row.name, target_file_type=row.target_file_type,  # type: ignore[arg-type]
            description=row.description, is_system=bool(row.is_system), version=row.version,
            created_at=row.created_at, updated_at=row.updated_at,
        )

    @staticmethod
    def _row_to_detail(row: PresetRow) -> Preset:
        return Preset(
            id=row.id, name=row.name, target_file_type=row.target_file_type,  # type: ignore[arg-type]
            description=row.description, template_md=row.template_md,
            sections_json=[PresetSection(**s) for s in _parse_json(row.sections_json, [])],
            frontmatter_json=_parse_json(row.frontmatter_json, {}),
            style_rules=_parse_json(row.style_rules, []),
            is_system=bool(row.is_system), version=row.version,
            created_at=row.created_at, updated_at=row.updated_at,
        )

    @staticmethod
    def _snapshot_dict(row: PresetRow) -> dict:
        """把当前预设行转成历史快照 dict。"""
        return {
            "name": row.name,
            "target_file_type": row.target_file_type,
            "description": row.description,
            "template_md": row.template_md,
            "sections": _parse_json(row.sections_json, []),
            "frontmatter": _parse_json(row.frontmatter_json, {}),
            "style_rules": _parse_json(row.style_rules, []),
        }

    @staticmethod
    def _save_version(session, row: PresetRow) -> None:
        """保存当前版本快照（create/update/restore 后调用）。"""
        session.add(PresetVersionRow(
            preset_id=row.id, version=row.version,
            snapshot_json=json.dumps(PresetService._snapshot_dict(row), ensure_ascii=False),
        ))

    def _get_row(self, session, preset_id: str) -> PresetRow:
        row = session.get(PresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"预设不存在：{preset_id}", details={"preset_id": preset_id})
        return row

    # ---------- 播种 ----------

    def seed_builtins(self) -> None:
        """首次启动播种 4 个默认预设（仅当 presets 表为空）。

        不做系统/用户区分：默认预设与用户预设完全一致，可自由修改/删除，
        删除后不会在下次启动时被重建。

        另对存量数据回填 template_md：早期版本内置预设只有 sections_json，
        此处若发现内置预设 template_md 为空则用内置模板文档补齐（不覆盖用户已改内容）。
        """
        with self.db.session() as s:
            if s.query(PresetRow).count() == 0:
                for data in BUILTIN_PRESETS:
                    template_md = BUILTIN_TEMPLATES.get(data["id"], "")
                    s.add(PresetRow(
                        id=data["id"], name=data["name"], target_file_type=data["target_file_type"],
                        description=data["description"],
                        template_md=template_md or None,
                        sections_json=json.dumps(data["sections"], ensure_ascii=False),
                        frontmatter_json=json.dumps(data["frontmatter"], ensure_ascii=False),
                        style_rules=json.dumps(data["style_rules"], ensure_ascii=False),
                        is_system=0, version=1,
                    ))
                s.commit()
                return
            # 存量回填：内置预设 template_md 为空 → 由现有 sections 反向合成模板
            # （保留用户已编辑的章节，不覆盖）
            for preset_id in BUILTIN_TEMPLATES:
                row = s.get(PresetRow, preset_id)
                if row is not None and not row.template_md:
                    secs = _parse_json(row.sections_json, [])
                    if not secs:
                        continue
                    row.template_md = self._synthesize_template(
                        row.name, row.target_file_type, [PresetSection(**x) for x in secs])
                    row.version += 1
                    row.updated_at = int(time.time())
            s.commit()

    @staticmethod
    def _synthesize_template(name: str, target_type: str, sections: list[PresetSection]) -> str:
        """旧数据（无 template_md）→ 由 sections_json 反向生成模板文档。"""
        secs = sorted(sections, key=lambda x: x.order)
        body = "\n\n".join(
            f"## {sec.title}\n\n"
            + (f"<!-- 提示：{sec.hint} -->\n" if sec.hint else "")
            + f"- 在此填写{sec.title}内容"
            for sec in secs
        )
        required = "\n".join(f"    - title: {sec.title}" for sec in secs)
        return (
            "---\n"
            "schema: soulforge.template/v1\n"
            f"target_file_type: {target_type}\n"
            "structure:\n"
            "  section_heading_level: 2\n"
            "  required_sections:\n"
            f"{required}\n"
            "  section_order: strict\n"
            "elements:\n"
            "  heading_style: atx\n"
            "  list_style: \"-\"\n"
            "  heading_blank_line: true\n"
            "  paragraph_blank_line: true\n"
            "typography:\n"
            "  max_heading_level: 3\n"
            "  allow_bold: true\n"
            "  allow_italic: true\n"
            "  forbid_emoji: true\n"
            "  forbid_raw_html: true\n"
            "modules:\n"
            "  frontmatter: optional\n"
            "---\n\n"
            f"# {name}\n\n{body}\n"
        )

    # ---------- CRUD ----------

    def list(self, target_file_type: str | None = None) -> list[PresetSummary]:
        with self.db.session() as s:
            q = s.query(PresetRow)
            if target_file_type:
                q = q.filter(PresetRow.target_file_type == target_file_type)
            rows = q.order_by(PresetRow.is_system.desc(), PresetRow.name).all()
            return [self._row_to_summary(r) for r in rows]

    def get(self, preset_id: str) -> Preset:
        with self.db.session() as s:
            return self._row_to_detail(self._get_row(s, preset_id))

    def create(self, payload: PresetCreate) -> Preset:
        """创建用户预设，is_system=False，保存 v1 快照。template_md 优先，sections 由其派生。"""
        now = int(time.time())
        sections = payload.sections_json
        if payload.template_md:
            sections = [PresetSection(**sec) for sec in derive_sections(payload.template_md)]
        with self.db.session() as s:
            row = PresetRow(
                id=f"preset-{uuid.uuid4().hex}",
                name=payload.name,
                target_file_type=payload.target_file_type,
                description=payload.description,
                template_md=payload.template_md,
                sections_json=json.dumps([sec.model_dump() for sec in sections], ensure_ascii=False),
                frontmatter_json=json.dumps(payload.frontmatter_json, ensure_ascii=False),
                style_rules=json.dumps(payload.style_rules, ensure_ascii=False),
                is_system=0, version=1, created_at=now, updated_at=now,
            )
            s.add(row)
            s.commit()
            self._save_version(s, row)
            s.commit()
            return self._row_to_detail(row)

    def update(self, preset_id: str, payload: PresetUpdate) -> Preset:
        """更新预设，version 自增 +1（所有预设均可修改全部字段）。"""
        with self.db.session() as s:
            row = self._get_row(s, preset_id)
            if payload.name is not None:
                row.name = payload.name
            if payload.target_file_type is not None:
                row.target_file_type = payload.target_file_type
            if payload.description is not None:
                row.description = payload.description
            if payload.template_md is not None:
                row.template_md = payload.template_md
                # 模板变更 → 派生更新 sections
                row.sections_json = json.dumps(
                    [sec.model_dump() for sec in
                     [PresetSection(**sec) for sec in derive_sections(payload.template_md)]], ensure_ascii=False)
            elif payload.sections_json is not None:
                row.sections_json = json.dumps([sec.model_dump() for sec in payload.sections_json], ensure_ascii=False)
            if payload.frontmatter_json is not None:
                row.frontmatter_json = json.dumps(payload.frontmatter_json, ensure_ascii=False)
            if payload.style_rules is not None:
                row.style_rules = json.dumps(payload.style_rules, ensure_ascii=False)
            row.version += 1
            row.updated_at = int(time.time())
            s.commit()
            self._save_version(s, row)
            s.commit()
            return self._row_to_detail(row)

    # ---------- 版本历史 ----------

    def list_versions(self, preset_id: str) -> list[PresetVersionInfo]:
        """列出预设版本历史（按版本倒序）。"""
        with self.db.session() as s:
            self._get_row(s, preset_id)  # 预设不存在 → 404
            rows = (s.query(PresetVersionRow)
                    .filter(PresetVersionRow.preset_id == preset_id)
                    .order_by(PresetVersionRow.version.desc(), PresetVersionRow.id.desc())
                    .all())
            out = []
            for r in rows:
                snap = _parse_json(r.snapshot_json, {})
                out.append(PresetVersionInfo(
                    id=r.id, preset_id=r.preset_id, version=r.version,
                    created_at=r.created_at, user=r.user,
                    name=snap.get("name", ""),
                    target_file_type=snap.get("target_file_type", "ANY"),
                    description=snap.get("description"),
                    template_md=snap.get("template_md"),
                    sections_json=[PresetSection(**sec) for sec in snap.get("sections", [])],
                    frontmatter_json=snap.get("frontmatter", {}),
                    style_rules=snap.get("style_rules", []),
                ))
            return out

    def restore_version(self, preset_id: str, version_id: int) -> Preset:
        """回溯到指定版本：应用历史快照，version 再 +1 并保存新快照。"""
        with self.db.session() as s:
            row = self._get_row(s, preset_id)
            vrow = s.get(PresetVersionRow, version_id)
            if vrow is None or vrow.preset_id != preset_id:
                raise PresetNotFoundError(
                    f"版本不存在：{version_id}", details={"preset_id": preset_id, "version_id": version_id})
            snap = _parse_json(vrow.snapshot_json, {})
            row.name = snap.get("name", row.name)
            row.target_file_type = snap.get("target_file_type", row.target_file_type)
            row.description = snap.get("description")
            row.template_md = snap.get("template_md") or None
            row.sections_json = json.dumps(snap.get("sections", []), ensure_ascii=False)
            row.frontmatter_json = json.dumps(snap.get("frontmatter", {}), ensure_ascii=False)
            row.style_rules = json.dumps(snap.get("style_rules", []), ensure_ascii=False)
            row.version += 1
            row.updated_at = int(time.time())
            s.commit()
            self._save_version(s, row)
            s.commit()
            return self._row_to_detail(row)

    def delete(self, preset_id: str) -> None:
        """删除预设（所有预设均可删除）。"""
        with self.db.session() as s:
            row = self._get_row(s, preset_id)
            s.delete(row)
            s.commit()

    # ---------- 应用（plan + execute） ----------

    @staticmethod
    def _has_section(content: str, title: str) -> bool:
        """判断 Markdown 内容里是否已存在某章节标题（任意标题层级）。"""
        pattern = re.compile(rf"^#{{1,6}}\s+{re.escape(title)}\s*$", re.MULTILINE)
        return bool(pattern.search(content))

    def _fill_missing_sections(self, content: str, preset: Preset, heading_level: int = 2) -> str:
        """按预设补齐缺失的必填章节（不动原有内容），标题层级遵循模板规则。"""
        missing = [
            sec for sec in sorted(preset.sections_json, key=lambda x: x.order)
            if sec.required and not self._has_section(content, sec.title)
        ]
        if not missing:
            return content
        parts = [content.rstrip("\n")]
        for sec in missing:
            parts.append(f"{'#' * heading_level} {sec.title}\n")
            if sec.hint:
                parts.append(f"<!-- {sec.hint} -->\n")
            parts.append("")
        return "\n".join(parts)

    def _rules_for(self, preset: Preset) -> TemplateRules:
        """解析预设的模板规则；无模板文档时由 sections 兜底构造。"""
        if preset.template_md:
            return parse_template(preset.template_md)
        return TemplateRules(
            name=preset.name, target_file_type=preset.target_file_type,
            required_sections=[
                RequiredSection(title=sec.title, required=sec.required)
                for sec in sorted(preset.sections_json, key=lambda x: x.order)
            ],
        )

    def apply_plan(self, preset_id: str, agent_id: str, file_path: str,
                   extra_instructions: str | None = None) -> PresetApplyPlan:
        """生成应用 plan（只读不写）：

        1. 解析模板规则（template_md → TemplateRules）
        2. 加载目标文档
        3. 按模板补齐缺失章节 → 机械性自动修正
        4. 格式校验（format_report），任何违规都展示给用户确认后再执行。
        """
        self._cleanup_expired()
        preset = self.get(preset_id)
        rules = self._rules_for(preset)
        current = self.file_manager.read_text(agent_id, file_path)
        filled = self._fill_missing_sections(current, preset, heading_level=rules.section_heading_level)
        proposed, format_report = FormatValidator().validate_and_fix(filled, rules)
        fromfile = f"{agent_id}/{file_path}"
        tofile = f"{agent_id}/{file_path}（应用预设 {preset.name}）"
        plan = PresetApplyPlan(
            plan_id=str(uuid.uuid4()),
            agent_id=agent_id, file_path=file_path, preset_id=preset_id,
            current_snapshot=current, proposed_content=proposed,
            unified_diff=unified_diff(current, proposed, fromfile=fromfile, tofile=tofile),
            lint_warnings=self.lint.lint_file(agent_id, file_path, proposed),
            format_report=format_report,
        )
        self._plans[plan.plan_id] = (time.time(), plan)
        return plan

    def apply_execute(self, plan_id: str, agent_id: str, file_path: str) -> PresetApplyResult:
        """执行应用：备份原文件 → 写入 → 审计（唯一写入口）。"""
        self._cleanup_expired()
        entry = self._plans.get(plan_id)
        if entry is None:
            raise PresetPlanNotFoundError(f"应用计划不存在或已清理：{plan_id}", details={"plan_id": plan_id})
        created_at, plan = entry
        if time.time() - created_at > PLAN_TTL_SECONDS:
            self._plans.pop(plan_id, None)
            raise PresetPlanExpiredError("应用计划已过期（>30 分钟），请重新生成", details={"plan_id": plan_id})
        if plan.agent_id != agent_id or plan.file_path != file_path:
            raise BadRequestError("plan 与请求的目标 Agent/文件不匹配")

        agent = self.file_manager.require_agent(agent_id)
        full = _safe_join(Path(agent.workspace), file_path)
        backup_id = None
        if full.is_file():
            backup_id = self.backup.backup(agent_id, file_path, full, reason="preset-apply")
        result = self.file_manager.write(agent_id, file_path, plan.proposed_content, auto_backup=False, audit=False)
        self.audit.record("preset_apply", agent_id, file_path,
                          {"backup_id": backup_id, "preset_id": plan.preset_id, "plan_id": plan_id})
        self._plans.pop(plan_id, None)
        return PresetApplyResult(backup_id=backup_id, applied_at=int(time.time()), file_size=result.size_bytes)
