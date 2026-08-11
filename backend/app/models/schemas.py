"""Pydantic 模型（API 层），与 SQLAlchemy Model 解耦。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["CORE", "MEMORY", "SKILL", "META", "OTHER"]
Severity = Literal["warning", "error"]
ImportStrategy = Literal["skip", "merge", "overwrite"]


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
