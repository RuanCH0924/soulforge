"""路由：配置中心（v1.0 项）—— 可视化读写 config.toml。

注：lint 严格模式 / 备份保留天数等改动立即生效；server.host/port 需重启服务。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.common import ok
from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api/config", tags=["config"])


class ServerCfg(BaseModel):
    host: str | None = None
    port: int | None = Field(None, ge=1, le=65535)


class BackupCfg(BaseModel):
    retention_days: int | None = Field(None, ge=1, le=3650, description="备份保留天数")
    auto_backup_on_write: bool | None = Field(None, description="写入前是否自动备份")


class LintCfg(BaseModel):
    enabled: bool | None = None
    strict_mode: bool | None = Field(None, description="严格模式：违规阻止保存")


class UICfg(BaseModel):
    default_theme: Literal["auto", "light", "dark"] | None = None
    default_view: Literal["tree", "list"] | None = None


class AdvancedCfg(BaseModel):
    show_skills: bool | None = None
    show_meta: bool | None = None
    show_memory: bool | None = None
    show_other: bool | None = None


class OpenClawCfg(BaseModel):
    dir: str | None = None


class ConfigUpdate(BaseModel):
    server: ServerCfg | None = None
    backup: BackupCfg | None = None
    lint: LintCfg | None = None
    ui: UICfg | None = None
    advanced: AdvancedCfg | None = None
    openclaw: OpenClawCfg | None = None


@router.get("")
def get_config(reg: Registry = Depends(get_registry)):
    """读取当前生效配置。"""
    return ok(reg.get_config_dict())


@router.put("")
def update_config(body: ConfigUpdate, reg: Registry = Depends(get_registry)):
    """局部更新配置（未传的字段保持不变），立即生效并写入 config.toml。"""
    patch = body.model_dump(exclude_none=True)
    return ok(reg.update_config(patch))
