"""路由：超级同步（Super Sync）——独立脚本的启停、状态、配置与日志。

与「跨 Agent 同步（/api/sync，plan+confirm 两步）」不同，超级同步是持续运行的
后台守护进程；本路由只做管理面（启停 / 状态 / 范围配置 / 日志）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.common import ok
from app.core.errors import BadRequestError
from app.deps import get_registry
from app.services import super_sync_common as ssc
from app.services.registry import Registry

router = APIRouter(prefix="/api/super-sync", tags=["super-sync"])


class SuperSyncConfigUpdate(BaseModel):
    interval_seconds: float | None = Field(None, ge=ssc.MIN_INTERVAL_SECONDS, le=ssc.MAX_INTERVAL_SECONDS)
    retention_days: int | None = Field(None, ge=ssc.MIN_RETENTION_DAYS, le=3650)
    agents: list[str] | None = None
    files: dict[str, list[str]] | None = None


def _parse_levels(levels: str | None) -> list[str] | None:
    if not levels:
        return None
    parsed = [lv.strip().upper() for lv in levels.split(",") if lv.strip()]
    invalid = [lv for lv in parsed if lv not in ssc.LOG_LEVELS]
    if invalid:
        raise BadRequestError(f"非法日志级别：{invalid}，可选 {list(ssc.LOG_LEVELS)}")
    return parsed or None


@router.get("/config")
def get_config(reg: Registry = Depends(get_registry)):
    """读取超级同步范围配置。"""
    return ok(reg.super_sync.get_config())


@router.put("/config")
def update_config(body: SuperSyncConfigUpdate, reg: Registry = Depends(get_registry)):
    """更新同步范围（参与 Agent 及每个 Agent 的文件清单）。"""
    return ok(reg.super_sync.update_config(body.model_dump(exclude_unset=True)))


@router.get("/status")
def get_status(reg: Registry = Depends(get_registry)):
    """运行状态（运行中 / 已停止 / 异常），含心跳与统计。"""
    return ok(reg.super_sync.get_status())


@router.post("/start")
def start(reg: Registry = Depends(get_registry)):
    """以独立进程启动超级同步（脱离主进程持续运行）。"""
    return ok(reg.super_sync.start(source="ui"))


@router.post("/stop")
def stop(reg: Registry = Depends(get_registry)):
    """停止独立运行的超级同步进程。"""
    return ok(reg.super_sync.stop())


@router.get("/logs")
def query_logs(
    levels: str | None = Query(None, description="逗号分隔日志级别，如 INFO,ERROR"),
    since: float | None = Query(None, description="起始 unix 秒（含）"),
    until: float | None = Query(None, description="结束 unix 秒（含）"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    reg: Registry = Depends(get_registry),
):
    """按级别 / 时间范围查询同步日志（倒序）。"""
    return ok(reg.super_sync.query_logs(
        levels=_parse_levels(levels), since=since, until=until, limit=limit, offset=offset,
    ))


@router.get("/logs/export")
def export_logs(
    levels: str | None = Query(None),
    since: float | None = Query(None),
    until: float | None = Query(None),
    reg: Registry = Depends(get_registry),
):
    """导出筛选后的日志（.jsonl 下载）。"""
    filename, payload = reg.super_sync.export_logs(
        levels=_parse_levels(levels), since=since, until=until,
    )
    return Response(
        content=payload,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
