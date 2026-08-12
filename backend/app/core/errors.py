"""Soulforge 错误体系：所有业务异常继承 SoulforgeError，统一映射 HTTP 状态码。"""
from __future__ import annotations


class SoulforgeError(Exception):
    """基类：API 层统一转成 {"error": {"code", "message", "details"}}。"""

    http_status: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "", details: dict | None = None):
        super().__init__(message or self.code)
        self.details = details or {}


class AgentNotFoundError(SoulforgeError):
    http_status = 404
    code = "AGENT_NOT_FOUND"


class FileNotFoundError(SoulforgeError):
    http_status = 404
    code = "FILE_NOT_FOUND"


class UnsafePathError(SoulforgeError):
    """路径穿越 / 越界。"""

    http_status = 403
    code = "UNSAFE_PATH"


class BackupFailedError(SoulforgeError):
    http_status = 500
    code = "BACKUP_FAILED"


class BadRequestError(SoulforgeError):
    http_status = 400
    code = "BAD_REQUEST"


class ConflictError(SoulforgeError):
    """乐观锁冲突 / lint 严格模式阻止保存。"""

    http_status = 409
    code = "CONFLICT"


class ManifestCorruptedError(SoulforgeError):
    http_status = 400
    code = "MANIFEST_CORRUPTED"


class SyncPlanExpiredError(SoulforgeError):
    http_status = 410
    code = "SYNC_PLAN_EXPIRED"


class SyncPlanNotFoundError(SoulforgeError):
    http_status = 404
    code = "SYNC_PLAN_NOT_FOUND"


class TemplateNotFoundError(SoulforgeError):
    http_status = 404
    code = "TEMPLATE_NOT_FOUND"


class UploadNotFoundError(SoulforgeError):
    http_status = 404
    code = "UPLOAD_NOT_FOUND"


class PresetNotFoundError(SoulforgeError):
    http_status = 404
    code = "PRESET_NOT_FOUND"


class PresetForbiddenError(SoulforgeError):
    """系统预设的删除 / 修改受保护字段。"""

    http_status = 403
    code = "PRESET_FORBIDDEN"


class PresetPlanNotFoundError(SoulforgeError):
    http_status = 404
    code = "PRESET_PLAN_NOT_FOUND"


class PresetPlanExpiredError(SoulforgeError):
    http_status = 410
    code = "PRESET_PLAN_EXPIRED"


class ProviderNotFoundError(SoulforgeError):
    http_status = 404
    code = "LLM_PROVIDER_NOT_FOUND"


class ProviderConflictError(SoulforgeError):
    """删除被 ai_jobs 引用的 provider。"""

    http_status = 409
    code = "LLM_PROVIDER_CONFLICT"


class UnsupportedProtocolError(SoulforgeError):
    http_status = 400
    code = "UNSUPPORTED_PROTOCOL"


class LLMRequestError(SoulforgeError):
    """LLM 上游调用失败（网络 / 鉴权 / 限流）。"""

    http_status = 502
    code = "LLM_REQUEST_FAILED"


class AIJobNotFoundError(SoulforgeError):
    http_status = 404
    code = "AI_JOB_NOT_FOUND"


class AIJobStatusError(SoulforgeError):
    """状态机非法流转（如对非 awaiting_confirm 的任务执行 apply）。"""

    http_status = 409
    code = "AI_JOB_STATUS"


class AIFileTooLargeError(SoulforgeError):
    """大文件（> 30KB）拒绝 AI 整理。"""

    http_status = 422
    code = "AI_FILE_TOO_LARGE"


class AILintBlockedError(SoulforgeError):
    """AI 输出未通过 lint，拒绝写入。"""

    http_status = 422
    code = "AI_LINT_BLOCKED"


class FormatViolationError(SoulforgeError):
    """输出文档未通过模板格式校验，拒绝写入。"""

    http_status = 422
    code = "FORMAT_VIOLATION"
