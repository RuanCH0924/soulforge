"""API 公共工具：统一响应包装。"""
from __future__ import annotations

import time
from typing import Any

from app import __version__


def ok(data: Any) -> dict:
    """成功响应：{data, meta:{timestamp, version}}（见 docs/API.md 2.1）。"""
    return {
        "data": data,
        "meta": {"timestamp": int(time.time()), "version": __version__},
    }


def error(code: str, message: str, details: dict | None = None) -> dict:
    """错误响应：{error:{code,message,details}}（见 docs/API.md 2.2）。"""
    payload = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return {"error": payload}
