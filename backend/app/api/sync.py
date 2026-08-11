"""路由：跨 Agent 同步（M5）—— 铁律：plan + confirm 两步。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import SyncExecuteRequest
from app.services.registry import Registry

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncPlanRequest(BaseModel):
    src_agent: str
    dst_agent: str
    files: list[str] = Field(..., min_length=1)


@router.post("/plan")
def sync_plan(body: SyncPlanRequest, reg: Registry = Depends(get_registry)):
    """生成同步计划（不写入，只算 diff）。"""
    result = reg.sync.plan(body.src_agent, body.dst_agent, body.files)
    return ok(result.model_dump())


@router.post("/execute")
def sync_execute(body: SyncExecuteRequest, reg: Registry = Depends(get_registry)):
    """执行同步计划（必须 plan 后 30 分钟内；用户确认的文件子集）。"""
    result = reg.sync.execute(body.plan_id, body.files)
    return ok(result.model_dump())
