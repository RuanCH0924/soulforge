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


class SyncPlanExpiredError(SoulforgeError):
    http_status = 410
    code = "SYNC_PLAN_EXPIRED"


class SyncPlanNotFoundError(SoulforgeError):
    http_status = 404
    code = "SYNC_PLAN_NOT_FOUND"


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


class DailySourceTooLargeError(SoulforgeError):
    """工作日志来源过大（分块摘要后仍超上限）→ 该日转人工复核，不做无上限的 token 消耗。"""

    http_status = 422
    code = "DAILY_SOURCE_TOO_LARGE"


class LLMOutputTruncatedError(SoulforgeError):
    """模型输出被 max_tokens 截断（响应 finish_reason = length / max_tokens）→ 文档不可能写完。

    与「强规则校验未通过」是两回事：前者是配额不够，后者是内容不合规。
    分开报错是为了让用户知道该去调 provider 的 `max_tokens`，而不是反复重跑。
    """

    http_status = 422
    code = "LLM_OUTPUT_TRUNCATED"


class DailyRunNotFoundError(SoulforgeError):
    http_status = 404
    code = "DAILY_RUN_NOT_FOUND"


class DailyRunStatusError(SoulforgeError):
    """批次状态机非法流转（如对非 awaiting_confirm 的批次执行 apply）。"""

    http_status = 409
    code = "DAILY_RUN_STATUS"


class DailyRunDisabledError(SoulforgeError):
    """执行被全局开关关闭（config.toml 的 daily_standardizer.dry_run_only=true）→ 只允许出计划。"""

    http_status = 403
    code = "DAILY_RUN_DISABLED"
