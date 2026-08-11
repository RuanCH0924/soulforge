"""路由：导入导出（M6）。导出返回 tar.gz；导入分 preview + execute 两步。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import ImportExecuteRequest
from app.services.registry import Registry

router = APIRouter(prefix="/api", tags=["export-import"])


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


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...),
                         target_agent_id: str = Form(...),
                         reg: Registry = Depends(get_registry)):
    """上传 tar.gz，解析 manifest + 校验 sha256 + 列出冲突。"""
    data = await file.read()
    result = reg.import_export.preview(data, target_agent_id)
    return ok(result.model_dump())


@router.post("/import/execute")
def import_execute(body: ImportExecuteRequest, reg: Registry = Depends(get_registry)):
    """执行导入（按冲突策略 skip / merge / overwrite）。"""
    result = reg.import_export.execute(body.upload_id, body.target_agent_id, body.conflicts)
    return ok(result.model_dump())
