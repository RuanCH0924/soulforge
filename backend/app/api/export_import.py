"""路由：Prompt Pack 导出（M6）。导出返回 tar.gz（单 Agent / 全部）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export/all")
def export_all(reg: Registry = Depends(get_registry)):
    """导出全部 Agent（一个 tarball，每个 Agent 一个子目录）。注意：必须先于 /export/{agent_id} 注册。"""
    path = reg.import_export.export_all()
    return FileResponse(path, media_type="application/gzip",
                        filename=path.name, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/export/{agent_id}")
def export_agent(agent_id: str, reg: Registry = Depends(get_registry)):
    """导出单个 Agent 的 Prompt Pack（.tar.gz）。"""
    path = reg.import_export.export_agent(agent_id)
    return FileResponse(path, media_type="application/gzip",
                        filename=path.name, headers={"X-Content-Type-Options": "nosniff"})
