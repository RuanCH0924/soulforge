"""路由：统计 & 仪表盘（M10）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import ok
from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats(reg: Registry = Depends(get_registry)):
    """首页仪表盘汇总数据。"""
    result = reg.stats.get_stats()
    return ok(result.model_dump())
