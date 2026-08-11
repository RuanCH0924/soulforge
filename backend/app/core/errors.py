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
