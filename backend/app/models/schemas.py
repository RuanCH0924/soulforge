"""Pydantic 模型（API 层），与 SQLAlchemy Model 解耦。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["CORE", "MEMORY", "SKILL", "META", "OTHER"]
Severity = Literal["warning", "error"]
ImportStrategy = Literal["skip", "merge", "overwrite"]
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


class SyncFilePlan(BaseModel):
    path: str
    similarity: float
    html_diff: str
    size_src: int
    size_dst: int


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


class ManifestFile(BaseModel):
    path: str
    size: int
    sha256: str


class Manifest(BaseModel):
    soulforge_version: str
    export_time: str
    agent_id: str
    files: list[ManifestFile]


class ConflictItem(BaseModel):
    path: str
    exists_in_target: bool
    target_size: int | None = None


class ImportPreviewResult(BaseModel):
    upload_id: str
    target_agent_id: str
    manifest: Manifest
    conflicts: list[ConflictItem]


class ImportExecuteRequest(BaseModel):
    upload_id: str
    target_agent_id: str
    conflicts: dict[str, ImportStrategy] = Field(default_factory=dict)


class ImportResultItem(BaseModel):
    file: str
    action: str  # skipped | overwritten | merged | added


class ImportExecuteResult(BaseModel):
    manifest: Manifest
    results: list[ImportResultItem]


class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    file_count: int


class TemplateApplyRequest(BaseModel):
    template_id: str
    new_agent_id: str
    target_workspace: str


class TemplateApplyResult(BaseModel):
    agent_id: str
    workspace: str
    files_created: list[str]


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
    version: int = 1
    created_at: int
    updated_at: int


class PresetApplyRequest(BaseModel):
    agent_id: str
    file_path: str
    extra_instructions: str | None = None


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
    agents_total: int
    files_total: int
    core_files: int
    memory_files: int
    backup_total: int
    backup_size_bytes: int
    lint_warnings_total: int
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


class Meta(BaseModel):
    timestamp: int
    version: str = "0.1.0"


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
