"""Pydantic 模型（API 层），与 SQLAlchemy Model 解耦。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app import __version__

Role = Literal["CORE", "MEMORY", "SKILL", "META", "OTHER"]
Severity = Literal["warning", "error"]
PresetTargetType = Literal["SOUL", "AGENTS", "MEMORY", "USER", "IDENTITY", "TOOLS", "WORKLOG", "ANY"]


class AgentInfo(BaseModel):
    id: str
    workspace: str
    display_name: str | None = None
    file_count: int = 0
    last_scanned_at: int | None = None
    created_at: int | None = None
    updated_at: int | None = None


class RecentFile(BaseModel):
    path: str
    mtime: int
    size_bytes: int


class AgentDetail(BaseModel):
    id: str
    workspace: str
    display_name: str | None = None
    file_count: int = 0
    last_scanned_at: int | None = None
    recent_files: list[RecentFile] = Field(default_factory=list)


class FileInfo(BaseModel):
    path: str = Field(..., description="相对 workspace 路径")
    role: Role
    size_bytes: int
    mtime: int
    sha256: str
    lint_warnings: int = 0
    last_lint_at: int | None = None


class FileContent(BaseModel):
    agent_id: str
    path: str
    role: Role
    content: str
    size_bytes: int
    mtime: int
    sha256: str


class WriteRequest(BaseModel):
    content: str = Field(..., description="写入的新内容")
    expected_sha256: str | None = Field(None, description="乐观锁：期望的旧 hash，不匹配返回 409")


class WriteResult(BaseModel):
    agent_id: str
    path: str
    size_bytes: int
    mtime: int
    sha256: str
    backup_id: int | None = None
    lint_warnings: int = 0


class BackupEntry(BaseModel):
    backup_id: int
    reason: str | None = None
    size_bytes: int
    sha256: str
    created_at: int


class SearchHit(BaseModel):
    agent_id: str
    file_path: str
    line_number: int
    line_content: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    hits: list[SearchHit]
    total: int
    duration_ms: int


class DiffResult(BaseModel):
    agent_a: str
    agent_b: str
    file: str
    similarity: float
    unified_diff: str
    html_diff: str
    #: 有效内容（归一化后）是否一致；一致时 unified_diff/html_diff 为空
    identical: bool = False
    #: 解释本次差异的格式噪声类型（空表示差异是真实业务差异）
    noise_kinds: list[str] = Field(default_factory=list, description="bom/line_ending/invisible_char/...")
    #: 归一化口径：strict | ignore_whitespace
    mode: str = "ignore_whitespace"


class SyncFilePlan(BaseModel):
    path: str
    similarity: float
    html_diff: str
    size_src: int
    size_dst: int
    #: 有效内容是否一致（一致时该文件无需同步）
    identical: bool = False
    noise_kinds: list[str] = Field(default_factory=list)


class SyncPlanResult(BaseModel):
    plan_id: str
    src_agent: str
    dst_agent: str
    files: list[SyncFilePlan]


class SyncExecuteRequest(BaseModel):
    plan_id: str
    files: list[str] = Field(..., description="用户确认要同步的文件子集")


class SyncResultItem(BaseModel):
    file: str
    status: str
    backup_id: int | None = None


class SyncExecuteResult(BaseModel):
    results: list[SyncResultItem]


class LintWarning(BaseModel):
    rule_id: str
    rule_name: str
    severity: Severity
    agent_id: str
    file_path: str
    line_number: int | None = None
    line_content: str | None = None
    suggestion: str


class LintStats(BaseModel):
    files_checked: int
    warnings: int
    errors: int


class LintAgentResult(BaseModel):
    agent_id: str
    warnings: list[LintWarning]
    stats: LintStats


class LintRuleInfo(BaseModel):
    """lint 规则目录项（`GET /api/lint/rules`）。

    规则文案的唯一事实源是 `LintService` 的规则类；前端与文档都从这里取，
    不各自再抄一份。
    """

    rule_id: str
    rule_name: str
    scope: Literal["file", "agent"] = Field(..., description="作用域：file = 逐文件检查；agent = 需要 Agent 全貌")
    severity: Severity
    description: str = Field(..., description="规则在检查什么（展示给用户）")


class ManifestFile(BaseModel):
    path: str
    size: int
    sha256: str


class Manifest(BaseModel):
    soulforge_version: str
    export_time: str
    agent_id: str
    files: list[ManifestFile]


class RollbackRequest(BaseModel):
    backup_id: int


class RollbackResult(BaseModel):
    file_path: str
    rolled_back_to: int
    new_backup_id: int
    sha256: str


# ---------- Phase 2.5 · M11 文档预设系统 ----------


class PresetSection(BaseModel):
    """预设的章节定义。"""

    title: str
    required: bool = True
    order: int = 1
    hint: str | None = None


class PresetCreate(BaseModel):
    name: str = Field(..., min_length=1, description="预设名")
    target_file_type: PresetTargetType
    description: str | None = None
    template_md: str | None = Field(None, description="标准 Markdown 模板文档（YAML 规则+骨架）")
    sections_json: list[PresetSection] = Field(default_factory=list, description="章节列表（由模板派生，可省略）")
    frontmatter_json: dict[str, str] = Field(default_factory=dict, description="frontmatter 模板")
    style_rules: list[str] = Field(default_factory=list, description="风格规则")


class PresetUpdate(BaseModel):
    """编辑预设（所有预设均可修改全部字段）。"""

    name: str | None = Field(None, min_length=1)
    target_file_type: PresetTargetType | None = None
    description: str | None = None
    template_md: str | None = None
    sections_json: list[PresetSection] | None = None
    frontmatter_json: dict[str, str] | None = None
    style_rules: list[str] | None = None


class PresetSummary(BaseModel):
    """列表项（不含 sections 等大字段）。"""

    id: str
    name: str
    target_file_type: PresetTargetType
    description: str | None = None
    is_system: bool = False
    # 是否内置预设（随版本分发，下次升级可能被刷新）——UI 展示「预设来源」用
    is_builtin: bool = False
    version: int = 1
    created_at: int
    updated_at: int


class Preset(BaseModel):
    """预设完整详情。"""

    id: str
    name: str
    target_file_type: PresetTargetType
    description: str | None = None
    template_md: str | None = None
    sections_json: list[PresetSection] = Field(default_factory=list)
    frontmatter_json: dict[str, str] = Field(default_factory=dict)
    style_rules: list[str] = Field(default_factory=list)
    is_system: bool = False
    is_builtin: bool = False
    version: int = 1
    created_at: int
    updated_at: int


class PresetApplyRequest(BaseModel):
    agent_id: str
    file_path: str
    extra_instructions: str | None = None


class PresetFromDocument(BaseModel):
    """由当前文档生成预设（编辑栏「设为预设」）。

    以编辑器当前内容作为模板正文，配合用户填写的参数生成带规则 frontmatter 的模板文档，
    从而得到一个可「应用预设 / AI 整理」复用的结构预设。
    """

    name: str = Field(..., min_length=1, description="预设名称")
    target_file_type: PresetTargetType = Field(..., description="适用文件类型")
    content: str = Field(..., min_length=1, description="作为模板正文的文档内容（编辑器当前内容）")
    description: str | None = Field(None, description="用途说明")
    section_heading_level: int = Field(
        2, ge=1, le=6, description="章节标题层级：该层级的标题构成预设的章节清单")
    required_sections: list[str] = Field(
        default_factory=list,
        description="必填章节（须为文档中该层级的标题）；留空 = 文档中该层级的全部标题",
    )
    section_order: Literal["strict", "loose"] = Field("strict", description="章节顺序是否严格")
    require_frontmatter: bool = Field(False, description="是否要求文档带 YAML frontmatter")


class PresetApplyExecuteRequest(BaseModel):
    plan_id: str
    agent_id: str
    file_path: str


class FormatViolation(BaseModel):
    rule_id: str
    rule_name: str
    line: int | None = None
    message: str = ""


class FormatReport(BaseModel):
    ok: bool
    violations: list[FormatViolation] = Field(default_factory=list)


class PresetApplyPlan(BaseModel):
    """应用预设生成的计算结果（不入库）。"""

    plan_id: str
    agent_id: str
    file_path: str
    preset_id: str
    current_snapshot: str
    proposed_content: str
    unified_diff: str
    lint_warnings: list[LintWarning] = Field(default_factory=list)
    format_report: FormatReport = Field(default_factory=lambda: FormatReport(ok=True))


class PresetApplyResult(BaseModel):
    backup_id: int | None
    applied_at: int
    file_size: int


class PresetVersionInfo(BaseModel):
    """预设版本历史条目（含快照，可恢复）。"""

    id: int
    preset_id: str
    version: int
    created_at: int
    user: str = "local"
    name: str
    target_file_type: PresetTargetType
    description: str | None = None
    template_md: str | None = None
    sections_json: list[PresetSection] = Field(default_factory=list)
    frontmatter_json: dict[str, str] = Field(default_factory=dict)
    style_rules: list[str] = Field(default_factory=list)


# ---------- Phase 2.5 · M12 LLM Provider 接入 ----------

LLMProtocol = Literal["openai-completions", "anthropic-messages"]


class LLMProviderCreate(BaseModel):
    id: str = Field(..., min_length=1, pattern=r"^[\w\-./]+$", description="provider 名（业务唯一）")
    base_url: str = Field(..., min_length=1, description="API 端点")
    api_key: str = Field(..., min_length=1, description="API key（明文，服务端加密存储）")
    model: str = Field(..., min_length=1)
    protocol: LLMProtocol
    enabled: bool = True
    max_tokens: int = Field(4096, ge=1, le=1_000_000)
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    timeout_seconds: int = Field(60, ge=1, le=600)


class LLMProviderUpdate(BaseModel):
    base_url: str | None = None
    api_key: str | None = Field(None, description="留空/None = 保留旧 key")
    model: str | None = None
    protocol: LLMProtocol | None = None
    enabled: bool | None = None
    max_tokens: int | None = Field(None, ge=1, le=1_000_000)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    timeout_seconds: int | None = Field(None, ge=1, le=600)


class LLMProviderOut(BaseModel):
    """Provider 输出（api_key 永远以掩码呈现）。"""

    id: str
    base_url: str
    api_key_masked: str
    model: str
    protocol: LLMProtocol
    enabled: bool
    max_tokens: int
    temperature: float
    timeout_seconds: int
    created_at: int
    updated_at: int


class LLMChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMChatRequest(BaseModel):
    provider_id: str
    messages: list[LLMChatMessage] = Field(..., min_length=1)
    max_tokens: int | None = None
    temperature: float | None = None


class LLMTokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponseOut(BaseModel):
    content: str
    usage: LLMTokenUsage = Field(default_factory=LLMTokenUsage)
    cost_estimate_usd: float = 0.0


class LLMTestResult(BaseModel):
    ok: bool
    latency_ms: int
    response_preview: str
    error: str | None = None


# ---------- Phase 2.5 · M13 AI 自动整理 ----------

AIJobStatus = Literal[
    "pending", "running", "awaiting_confirm", "applied", "rejected", "failed", "superseded"
]


class AIJobCreate(BaseModel):
    agent_id: str
    file_path: str
    preset_id: str
    provider_id: str
    extra_instructions: str | None = None


class AIRegenerateRequest(BaseModel):
    extra_instructions: str = Field(..., description="重新生成时的新指令")


class AIJobDiffPlan(BaseModel):
    unified_diff: str
    lint_warnings: list[LintWarning] = Field(default_factory=list)
    format_report: FormatReport = Field(default_factory=lambda: FormatReport(ok=True))


class AIJobSummary(BaseModel):
    """列表项。"""

    id: str
    agent_id: str
    file_path: str
    preset_id: str
    provider_id: str
    status: AIJobStatus
    created_at: int
    updated_at: int
    finished_at: int | None = None
    superseded_by: str | None = None


class AIJob(AIJobSummary):
    """任务完整详情。"""

    input_snapshot: str | None = None
    output_content: str | None = None
    diff_plan_json: AIJobDiffPlan | None = None
    extra_instructions: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_estimate_usd: float | None = None
    error: str | None = None


class AIJobCreateResult(BaseModel):
    job_id: str
    status: AIJobStatus
    created_at: int


class AIJobApplyResult(BaseModel):
    job_id: str
    status: AIJobStatus
    backup_id: int | None = None
    file_size: int = 0


class AgentBackupGroup(BaseModel):
    file_path: str
    backups: list[BackupEntry]


class AgentBackupsResult(BaseModel):
    agent_id: str
    files: list[AgentBackupGroup]


class ScanResult(BaseModel):
    agents_scanned: int
    files_indexed: int
    duration_ms: int


class StatsResult(BaseModel):
    """统计面板数据。

    **不含 lint 警告数**：该指标需实时跑 lint 才能得到（`files.lint_warnings` 索引列
    从不被扫描填充，取索引只会得到恒为 0 的假数据）。UI 的 lint 计数统一取自
    `GET /api/lint/all`（与「检查报告」同源），见 docs/API.md。
    """

    agents_total: int
    files_total: int
    core_files: int
    memory_files: int
    backup_total: int
    backup_size_bytes: int
    last_scan_at: int | None = None
    disk_usage_bytes: int


class AuditEntry(BaseModel):
    id: int
    timestamp: int
    action: str
    agent_id: str | None = None
    target_path: str | None = None
    details_json: str | None = None
    user: str = "local"
    result: str = "ok"


# ---------- M15 · 工作日志标准化（P2 批次） ----------


class DailySourceInfo(BaseModel):
    """一个来源在归并前后的体积与剥壳事实。"""

    path: str
    kind: Literal["A", "B", "C"]
    raw_bytes: int
    clean_bytes: int
    removed_total: int = 0
    summarized: bool = False   # 是否经「分块摘要」
    chunks: int = 0


class DailyRunItem(BaseModel):
    """批次的逐日条目。"""

    date: str
    target_path: str
    has_standard: bool = False
    sources: list[DailySourceInfo] = Field(default_factory=list)
    fragments_to_delete: list[str] = Field(default_factory=list)
    output_content: str | None = None
    unified_diff: str | None = None
    html_diff: str | None = None
    format_report: FormatReport = Field(default_factory=lambda: FormatReport(ok=False))
    lint_warnings: list[LintWarning] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    empty_reason: str | None = None  # 非空 = 模型判定「本日无可归档内容」（不产出日文件，只清碎片）
    decision: str = "pending"        # pending | applied | skipped
    status: str = "pending"          # pending|planned|failed|blocked|applied|partially_applied|skipped|empty
    error: str | None = None
    backup_id: int | None = None
    applied_at: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0


class DailyRunSummary(BaseModel):
    id: str
    agent_id: str
    date_from: str
    date_to: str
    preset_id: str
    preset_version: int = 1
    provider_id: str
    status: str
    days_total: int = 0
    token_budget: int = 0
    tokens_used: int = 0
    cost_estimate_usd: float = 0.0
    error: str | None = None
    created_at: int
    updated_at: int
    finished_at: int | None = None


class DailyRun(DailyRunSummary):
    extra_instructions: str | None = None
    items: list[DailyRunItem] = Field(default_factory=list)


class DailyRunCreate(BaseModel):
    agent_id: str
    date_from: str = Field(..., description="YYYY-MM-DD")
    date_to: str = Field(..., description="YYYY-MM-DD")
    preset_id: str = Field("preset-wlog-daily-std", description="技能预设（默认「工作日志日标准化」）")
    provider_id: str
    extra_instructions: str | None = None


class DailyRunCreateResult(BaseModel):
    run_id: str
    status: str
    days_total: int
    reused: bool = False      # 命中幂等键 → 复用既有批次，未产生新的 LLM 调用
    created_at: int


class DailyRunApplyRequest(BaseModel):
    dates: list[str] = Field(default_factory=list, description="要应用的日期；为空且 apply_all=false 时视为无操作")
    apply_all: bool = Field(False, description="整批应用（等价于列出全部 pending 日）")


class DailyRunApplyResult(BaseModel):
    run_id: str
    status: str
    applied: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)     # 日文件已写，碎片删失败
    blocked: list[str] = Field(default_factory=list)     # 写前验收不过，未写入
    failed: list[str] = Field(default_factory=list)
    no_content: list[str] = Field(default_factory=list)  # 判定无可归档内容：未产出日文件，仅清理碎片
    skipped: list[str] = Field(default_factory=list)


class DailyRunSkipRequest(BaseModel):
    dates: list[str] = Field(..., min_length=1)


class DailyRunReportItem(BaseModel):
    """单日的验收结果（对手写盘后的真实文件核对）。"""

    date: str
    target_path: str
    status: str = "pending"          # 该日的 item 状态
    empty: bool = False              # 该日判定「无可归档内容」：不产出日文件，只核对碎片是否已清
    delivered: bool = False          # 该日是否已交付（applied / partially_applied）
    single_file: bool = True         # memory/ 顶层该日期只剩目标文件
    naming_ok: bool = True           # 命名合规 memory/YYYY-MM-DD.md
    sections_ok: bool = True         # 必填章节齐全 + 顺序正确（对磁盘内容跑强规则）
    no_residue: bool = True          # 12 类低价值元数据残留 = 0
    fragments_gone: bool = True      # 拟删碎片已不在磁盘上
    details: list[str] = Field(default_factory=list)


class DailyRunReport(BaseModel):
    run_id: str
    agent_id: str
    status: str
    passed: bool
    items: list[DailyRunReportItem] = Field(default_factory=list)
    days_delivered: int = 0
    days_total: int = 0
    tokens_used: int = 0
    cost_estimate_usd: float = 0.0
    generated_at: int


class Meta(BaseModel):
    timestamp: int
    version: str = __version__


class Envelope(BaseModel):
    """通用响应包装：{data, meta}。"""

    data: dict
    meta: Meta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
