"""路由：审计日志（v1.0：审计 UI 的后端接口）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def audit_log(limit: int = Query(100, ge=1, le=500),
              offset: int = Query(0, ge=0),
              agent_id: str | None = Query(None),
              action: str | None = Query(None),
              reg: Registry = Depends(get_registry)):
    """查询审计日志（按时间倒序，可按 Agent / 操作类型过滤）。"""
    entries = reg.audit.query(limit=limit, offset=offset, agent_id=agent_id, action=action)
    return ok([e.model_dump() for e in entries])
