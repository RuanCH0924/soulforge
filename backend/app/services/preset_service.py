"""PresetService（M11 · 文档预设系统，Phase 2.5 Step 1）。

职责：
- 预设 CRUD（内置预设与用户预设同等可编辑、可删除；version 自增 + 版本快照）
- 内置预设播种（4 个，与用户预设同等可编辑；首次空表全量播种，存量安装补种新增项）
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
    PresetFromDocument,
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

# ---------- 预设两类用途的边界（UI-SPECS §5.7） ----------
# 「专供大模型处理工作日志」的预设类型 = M15 日志标准化的规则载体。
# 这类预设**不出现在** 系统配置 → 文档预设，也不出现在主工作台「应用预设」下拉；
# 只在 业务工具 → 日志标准化界面（及其 API）里可见、可编辑。
# 判据就是类型本身，不额外加开关字段：M15 的预设选择器本来就只列 WORKLOG。
DAILY_PRESET_TYPE = "WORKLOG"

# `list()` 的可选范围：workbench = 主工作台 / 设置页（排除大模型专用预设）
SCOPE_ALL = "all"
SCOPE_WORKBENCH = "workbench"
SCOPES: tuple[str, ...] = (SCOPE_ALL, SCOPE_WORKBENCH)

PLAN_TTL_SECONDS = 30 * 60  # apply plan ≤ 30 分钟有效（与 sync plan 一致）

# 「设为预设」的模板正文体积上限：模板全文会注入 AI 提示词，过大将撑爆 token 预算
MAX_TEMPLATE_BYTES = 30 * 1024

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")


def _scan_headings(content: str) -> list[tuple[int, str]]:
    """扫描 Markdown 标题（跳过围栏代码块），返回 [(level, title)]，保持文档顺序。"""
    out: list[tuple[int, str]] = []
    in_fence = False
    for raw in content.split("\n"):
        line = raw.rstrip()
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_LINE_RE.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2).rstrip("#").strip()))
    return out


def _parse_json(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default

# 内置预设（v1）：id 前缀 preset-，见 docs/ROADMAP.md 2.3 / docs/MEMORY-DAILY-STANDARDIZER-PLAN.md
# 播种时 is_system=0（与用户预设同等可编辑、可删除）
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
    # 注：原「工作日志汇总」（preset-wlog-summary）已退役 —— 它与本条是同一件事的两种口径
    # （单文件整理 vs 逐日归并），两个并列选项让用户无法判断该选哪个。现将它的归档顺序规则与
    # 「明日计划」章节并入本条，WORKLOG 类型只保留一个预设。退役 id 见 BUILTIN_PRESETS_RETIRED。
    {
        "id": "preset-wlog-daily-std",
        "name": "工作日志日标准化",
        "target_file_type": "WORKLOG",
        "description": (
            "把同一天的多份来源（日文件 / session 导出 / 主题碎片）归并成 1 份标准工作日志"
            "并清理碎片；也可用于整理已有的单份 memory/YYYY-MM-DD.md"
        ),
        "sections": [
            {"title": "一、今日概览", "required": True, "order": 1, "hint": "1~3 条概括当天最重要的事"},
            {"title": "二、关键事件", "required": True, "order": 2, "hint": "每个事件写 事实 / 原因 / 结果"},
            {"title": "三、关键决策", "required": True, "order": 3, "hint": "用户做出的选择与配置变更"},
            {"title": "四、待办事项", "required": True, "order": 4, "hint": "未解决的问题与后续安排"},
            {"title": "五、明日计划", "required": True, "order": 5, "hint": "下一步安排；无明确计划时写「无」"},
        ],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
        "style_rules": [
            (
                "保留：明确问题与根因、修复方案与结果、用户做出的选择、配置项含义与变更、"
                "模型/工具/技能/cron 行为、安全审计结果、可复用数据（余额、盘中收盘、日报）、"
                "文档与文件产出、未决问题与待办"
            ),
            (
                "删除：Session Key / Session ID / Source、Conversation info (untrusted metadata) 整段 JSON、"
                "Sender (untrusted metadata) 整段 JSON、Reply target of current user message 上下文壳、"
                "Queued messages while agent was busy、重复的「让我检查一下」「我来看看」「任务还在运行中」、"
                "单纯重复的 HEARTBEAT_OK 记录"
            ),
            "只保留结论，不保留过程：多轮状态轮询、重复的失败重试日志、调试中间态、同一问题的重复解释",
            "改写成客观记录：去掉「喵呜～」「蹭蹭～」「给主人看看」「我来帮你查一下」等对话腔与过渡语，只保留事实",
            "默认不做敏感信息脱敏：仅当用户明确要求过滤敏感信息时，才处理密钥、open_id、token 等",
            "整理目标是有用而非最短：不为了精简而牺牲长期可检索的事实",
            # 并入原「工作日志汇总」的两条口径（归档顺序 + 不保留流水账）；
            # 它的第三条「口语化禁令」已由上面的「改写成客观记录」覆盖，故不重复
            "按时间倒序归档：同一天内的事项按发生时间倒序排列；只提取关键决策与关键事件，不保留流水账",
        ],
    },
]

# 随版本新增的内置预设（append-only 白名单）：存量安装（presets 表非空）只补种这些，
# 不重建上表其余内置预设 —— 用户可能已主动删除它们，升级时塞回来属于数据污染。
# 维护规则：每次新增内置预设就把 id 追加到末尾；已进入名单的不要移除
#（否则跨版本升级、跳过中间版本的安装会永久漏掉该预设）。
BUILTIN_PRESETS_ADDED: tuple[str, ...] = ("preset-wlog-daily-std",)

# 全部内置预设 id（随版本分发的那些）：`Preset.is_builtin` 用它区分
# 「内置预设（下次升级可能被刷新）」与「用户自建」——UI 上用于展示预设来源。
BUILTIN_PRESET_IDS: frozenset[str] = frozenset(d["id"] for d in BUILTIN_PRESETS)

# ---------- 存量安装的内置预设迁移（内容锚点）----------
# 下面两张表的 value 都是「该预设上一版发布时的定义」，作用是**判断用户改过没有**：
# 库里那条预设若仍与该定义逐字段一致，说明它一直是我们发出去的样子，可以安全升级/下线；
# 不一致说明用户编辑过 —— 那是用户自己的资产，一律不动。
# 只比对内容字段（name / target_type / description / sections / style_rules），不含 template_md：
# 老安装的 template_md 可能由「存量回填」自动合成，不等于内置模板常量，不能当改动信号。
#
# 维护规则：每次要修订某个内置预设的内容 → 把「修订前的定义」补进 REFRESHED 再改 BUILTIN_PRESETS；
# 每次要下线某个内置预设 → 从 BUILTIN_PRESETS 删掉，把「下线的定义」记进 RETIRED（append-only）。

# 内容有更新的内置预设：存量安装上，库中内容 == 这里记的上一版 → 覆盖为 BUILTIN_PRESETS 里的最新定义
BUILTIN_PRESETS_REFRESHED: dict[str, dict] = {
    "preset-wlog-daily-std": {
        "name": "工作日志日标准化",
        "target_file_type": "WORKLOG",
        "description": "逐日归并 memory/ 下的日文件：每天只留 1 个 YYYY-MM-DD.md，剥离元数据壳与对话腔噪音",
        "sections": [
            {"title": "一、今日概览", "required": True, "order": 1, "hint": "1~3 条概括当天最重要的事"},
            {"title": "二、关键事件", "required": True, "order": 2, "hint": "每个事件写 事实 / 原因 / 结果"},
            {"title": "三、关键决策", "required": True, "order": 3, "hint": "用户做出的选择与配置变更"},
            {"title": "四、待办事项", "required": True, "order": 4, "hint": "未解决的问题与后续安排"},
        ],
        "style_rules": [
            (
                "保留：明确问题与根因、修复方案与结果、用户做出的选择、配置项含义与变更、"
                "模型/工具/技能/cron 行为、安全审计结果、可复用数据（余额、盘中收盘、日报）、"
                "文档与文件产出、未决问题与待办"
            ),
            (
                "删除：Session Key / Session ID / Source、Conversation info (untrusted metadata) 整段 JSON、"
                "Sender (untrusted metadata) 整段 JSON、Reply target of current user message 上下文壳、"
                "Queued messages while agent was busy、重复的「让我检查一下」「我来看看」「任务还在运行中」、"
                "单纯重复的 HEARTBEAT_OK 记录"
            ),
            "只保留结论，不保留过程：多轮状态轮询、重复的失败重试日志、调试中间态、同一问题的重复解释",
            "改写成客观记录：去掉「喵呜～」「蹭蹭～」「给主人看看」「我来帮你查一下」等对话腔与过渡语，只保留事实",
            "默认不做敏感信息脱敏：仅当用户明确要求过滤敏感信息时，才处理密钥、open_id、token 等",
            "整理目标是有用而非最短：不为了精简而牺牲长期可检索的事实",
        ],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
    },
}

# 已退役的内置预设：存量安装上，库中内容 == 这里记的最后一版 → 标记 retired_at（列表里不再出现）。
# 行本身保留（不删行），以免历史上引用它的批次 / AI 任务读取时报 404。
BUILTIN_PRESETS_RETIRED: dict[str, dict] = {
    # 与原「工作日志汇总」合并为 preset-wlog-daily-std（见 BUILTIN_PRESETS 里的说明）
    "preset-wlog-summary": {
        "name": "工作日志汇总",
        "target_file_type": "WORKLOG",
        "description": "整理 memory/YYYY-MM-DD.md：按时间倒序归档、提取关键决策",
        "sections": [
            {"title": "今日概览", "required": True, "order": 1, "hint": "当日核心成果"},
            {"title": "关键决策", "required": True, "order": 2, "hint": "值得长期记住的决定"},
            {"title": "待办与风险", "required": True, "order": 3, "hint": "未完成事项与隐患"},
            {"title": "明日计划", "required": True, "order": 4, "hint": "下一步安排"},
        ],
        "style_rules": ["按时间倒序归档", "只提取关键决策，不保留流水账", "口语化禁令"],
        "frontmatter": {"schema": "soulforge.preset/v1", "owner": "user"},
    },
}


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
            description=row.description, is_system=bool(row.is_system),
            is_builtin=row.id in BUILTIN_PRESET_IDS, version=row.version,
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
            is_system=bool(row.is_system), is_builtin=row.id in BUILTIN_PRESET_IDS,
            version=row.version,
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

    @staticmethod
    def _apply_definition(row: PresetRow, data: dict) -> None:
        """把内置定义写进一行（内容字段全覆盖，不动 version / 时间戳 / 退役标记）。"""
        row.name = data["name"]
        row.target_file_type = data["target_file_type"]
        row.description = data["description"]
        row.template_md = BUILTIN_TEMPLATES.get(data["id"]) or None
        row.sections_json = json.dumps(data["sections"], ensure_ascii=False)
        row.frontmatter_json = json.dumps(data["frontmatter"], ensure_ascii=False)
        row.style_rules = json.dumps(data["style_rules"], ensure_ascii=False)

    @classmethod
    def _new_builtin_row(cls, data: dict) -> PresetRow:
        """构造一条内置预设行（is_system=0：与用户预设同等可编辑、可删除）。"""
        row = PresetRow(id=data["id"], is_system=0, version=1)
        cls._apply_definition(row, data)
        return row

    @staticmethod
    def _matches_definition(row: PresetRow, data: dict) -> bool:
        """库中该预设的内容是否与给定定义一致（判定「用户改过没有」/「已是这一版」）。

        只比对内容字段，不含 template_md：老安装的 template_md 可能由「存量回填」
        自动合成，与内置模板常量不同，不能当改动信号。
        JSON 字段按解析后的结构比对，避免受写入时的空格 / 转义差异影响。
        """
        return (
            row.name == data["name"]
            and row.target_file_type == data["target_file_type"]
            and row.description == data["description"]
            and _parse_json(row.sections_json, []) == data["sections"]
            and _parse_json(row.frontmatter_json, {}) == data["frontmatter"]
            and _parse_json(row.style_rules, []) == data["style_rules"]
        )

    def seed_builtins(self) -> None:
        """播种内置预设（启动时调用）。

        - 首次启动（presets 表为空）→ 按当前 BUILTIN_PRESETS 全量播种
        - 存量安装（表非空）→ 三件事，且都只作用于**内容仍是内置定义**的预设
          （用户改过的一律不动，那是用户自己的资产）：
          ① 补种 BUILTIN_PRESETS_ADDED（随版本新增的）
          ② 刷新 BUILTIN_PRESETS_REFRESHED（内容有更新的，覆盖为新定义）
          ③ 退役 BUILTIN_PRESETS_RETIRED（已下线的，标记 retired_at）
          不重建用户已删除的历史内置预设
        - 存量回填：早期版本内置预设只有 sections_json，template_md 为空则用内置
          模板文档补齐（保留用户已改内容）

        所有内置预设 is_system=0，即与用户预设同等可编辑、可自由删除。
        播种/补种时写入 v1 版本快照，该快照同时充当「已补种」标记：
        用户日后删掉它，启动流程不会再塞回来（删除即视为已知悉并拒绝）。
        """
        with self.db.session() as s:
            if s.query(PresetRow).count() == 0:
                for data in BUILTIN_PRESETS:
                    row = self._new_builtin_row(data)
                    s.add(row)
                    s.flush()
                    self._save_version(s, row)
                s.commit()
                return
            # ① 存量安装：补种本版本新增的内置预设；已有版本快照说明补种过（用户后来删了）
            for data in BUILTIN_PRESETS:
                preset_id = data["id"]
                if preset_id not in BUILTIN_PRESETS_ADDED or s.get(PresetRow, preset_id) is not None:
                    continue
                seeded = (s.query(PresetVersionRow)
                          .filter(PresetVersionRow.preset_id == preset_id).count())
                if seeded:
                    continue
                row = self._new_builtin_row(data)
                s.add(row)
                s.flush()
                self._save_version(s, row)
            # ② 存量安装：内置预设内容随版本更新（仅在内容仍是上一版发布的样子时覆盖）
            for preset_id, prev_def in BUILTIN_PRESETS_REFRESHED.items():
                row = s.get(PresetRow, preset_id)
                data = next((d for d in BUILTIN_PRESETS if d["id"] == preset_id), None)
                if row is None or data is None or self._matches_definition(row, data):
                    continue
                if not self._matches_definition(row, prev_def):
                    continue
                self._apply_definition(row, data)
                row.version += 1
                row.updated_at = int(time.time())
                self._save_version(s, row)
            # ③ 存量安装：退役已下线的内置预设（仅在内容仍是最后一版发布的样子时隐藏）
            for preset_id, last_def in BUILTIN_PRESETS_RETIRED.items():
                row = s.get(PresetRow, preset_id)
                if row is None or row.retired_at is not None:
                    continue
                if self._matches_definition(row, last_def):
                    row.retired_at = int(time.time())
                    row.updated_at = int(time.time())
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
    def _yaml_str(value: str) -> str:
        """把自由文本安全地写成 YAML 双引号标量（JSON 字符串与 YAML flow 标量兼容）。"""
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _compose_template(
        *,
        name: str,
        target_type: str,
        section_titles: list[str],
        body: str,
        section_heading_level: int = 2,
        section_order: str = "strict",
        max_heading_level: int = 3,
        frontmatter_required: bool = False,
        title: str | None = None,
    ) -> str:
        """拼装标准模板文档：YAML 规则 frontmatter +（可选 H1 标题）+ 正文骨架。"""
        required = "\n".join(f"    - title: {t}" for t in section_titles)
        title_block = f"# {title}\n\n" if title else ""
        return (
            "---\n"
            "schema: soulforge.template/v1\n"
            f"name: {PresetService._yaml_str(name)}\n"
            f"target_file_type: {target_type}\n"
            "structure:\n"
            f"  section_heading_level: {section_heading_level}\n"
            "  required_sections:\n"
            f"{required}\n"
            f"  section_order: {section_order}\n"
            "elements:\n"
            "  heading_style: atx\n"
            "  list_style: \"-\"\n"
            "  heading_blank_line: true\n"
            "  paragraph_blank_line: true\n"
            "typography:\n"
            f"  max_heading_level: {max_heading_level}\n"
            "  allow_bold: true\n"
            "  allow_italic: true\n"
            "  forbid_emoji: true\n"
            "  forbid_raw_html: true\n"
            "modules:\n"
            f"  frontmatter: {'required' if frontmatter_required else 'optional'}\n"
            "---\n\n"
            f"{title_block}{body}\n"
        )

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
        return PresetService._compose_template(
            name=name, target_type=target_type,
            section_titles=[sec.title for sec in secs], body=body, title=name,
        )

    # ---------- CRUD ----------

    def list(self, target_file_type: str | None = None,
             scope: str = SCOPE_ALL) -> list[PresetSummary]:
        """列出可选预设。已退役的内置预设（retired_at 非空）不出现，但 get() 仍可取到。

        `scope=workbench` → 排除大模型专用预设（见 `DAILY_PRESET_TYPE`）：
        主工作台「应用预设」与设置页「文档预设」都走这一档，两类预设因此不会混淆。
        """
        if scope not in SCOPES:
            raise BadRequestError(
                f"非法 scope：{scope!r}，可选 {'/'.join(SCOPES)}",
                details={"scope": scope, "allowed": list(SCOPES)})
        with self.db.session() as s:
            q = s.query(PresetRow).filter(PresetRow.retired_at.is_(None))
            if target_file_type:
                q = q.filter(PresetRow.target_file_type == target_file_type)
            if scope == SCOPE_WORKBENCH:
                q = q.filter(PresetRow.target_file_type != DAILY_PRESET_TYPE)
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

    def create_from_document(self, payload: PresetFromDocument) -> Preset:
        """由当前文档生成预设（编辑栏「设为预设」）。

        以编辑器当前内容作为模板正文；章节清单取自文档中指定层级的标题，
        `required_sections` 作为其子集过滤（顺序仍按文档出现顺序）。
        """
        body = payload.content.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        size = len(body.encode("utf-8"))
        if size > MAX_TEMPLATE_BYTES:
            raise BadRequestError(
                f"文档 {size // 1024}KB 超过 {MAX_TEMPLATE_BYTES // 1024}KB 上限："
                "预设模板全文会注入 AI 提示词，请先精简文档再存为预设",
                details={"size_bytes": size, "limit_bytes": MAX_TEMPLATE_BYTES})

        headings = _scan_headings(body)
        level = payload.section_heading_level
        detected: list[str] = []
        for lv, title in headings:
            if lv == level and title not in detected:
                detected.append(title)
        if not detected:
            raise BadRequestError(
                f"文档中未发现 {'#' * level} 级标题，无法据此生成预设章节",
                details={"section_heading_level": level})
        if payload.required_sections:
            wanted = set(payload.required_sections)
            required = [t for t in detected if t in wanted]
            if not required:
                raise BadRequestError(
                    "所勾选的必填章节在文档中不存在，请重新选择",
                    details={"required_sections": payload.required_sections})
        else:
            required = detected

        template_md = self._compose_template(
            name=payload.name,
            target_type=payload.target_file_type,
            section_titles=required,
            body=body,
            section_heading_level=level,
            section_order=payload.section_order,
            max_heading_level=max([lv for lv, _ in headings] + [level]),
            frontmatter_required=payload.require_frontmatter,
        )
        return self.create(PresetCreate(
            name=payload.name,
            target_file_type=payload.target_file_type,
            description=payload.description,
            template_md=template_md,
        ))

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

    def rules_for(self, preset: Preset) -> TemplateRules:
        """解析预设的模板规则；无模板文档时由 sections 兜底构造。

        公开方法：AI 整理（M13）与工作日志归并（M15）都要用同一口径解析预设规则，
        避免各服务各写一份副本。
        """
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
        rules = self.rules_for(preset)
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
