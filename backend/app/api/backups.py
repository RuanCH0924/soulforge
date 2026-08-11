"""路由：备份与回滚（M7）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import AgentBackupsResult, RollbackRequest
from app.services.registry import Registry

router = APIRouter(prefix="/api/backups", tags=["backups"])


class RollbackBody(RollbackRequest):
    pass


@router.get("/{agent_id}")
def list_backups(agent_id: str, reg: Registry = Depends(get_registry)):
    """列出 Agent 的所有备份（按文件分组）。"""
    reg.file_manager.require_agent(agent_id)
    groups = reg.backup.list_for_agent(agent_id)
    files = [
        {"file_path": fp, "backups": [b.model_dump() for b in backups]}
        for fp, backups in groups
    ]
    return ok(AgentBackupsResult(agent_id=agent_id, files=files).model_dump())


@router.post("/{agent_id}/{file_path}/rollback")
def rollback(agent_id: str, file_path: str, body: RollbackBody,
             reg: Registry = Depends(get_registry)):
    """回滚到指定备份（回滚前先备份当前状态，避免丢数据）。"""
    result = reg.file_manager.rollback(agent_id, file_path, body.backup_id)
    return ok(result.model_dump())
