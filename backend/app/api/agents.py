"""路由：Agent 管理（M1）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import AgentDetail, AgentInfo, RecentFile, ScanResult
from app.services.registry import Registry

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents(reg: Registry = Depends(get_registry)):
    """列出全部 Agent。"""
    return ok([a.model_dump() for a in reg.file_manager.list_agents()])


@router.get("/{agent_id}")
def get_agent(agent_id: str, reg: Registry = Depends(get_registry)):
    """单个 Agent 详情（含最近活动的文件）。"""
    info: AgentInfo = reg.discovery.require(agent_id)
    files = reg.file_manager.list(agent_id)
    recent = sorted(files, key=lambda f: f.mtime, reverse=True)[:5]
    detail = AgentDetail(
        id=info.id,
        workspace=info.workspace,
        display_name=info.display_name,
        file_count=len(files),
        last_scanned_at=info.last_scanned_at,
        recent_files=[RecentFile(path=f.path, mtime=f.mtime, size_bytes=f.size_bytes) for f in recent],
    )
    return ok(detail.model_dump())


@router.post("/scan")
def scan(reg: Registry = Depends(get_registry)):
    """重新扫描所有 Agent workspace，重建索引。"""
    result: ScanResult = reg.file_manager.scan_all()
    return ok(result.model_dump())
