"""路由：文件浏览 / 编辑（M2）+ 跨 Agent 编辑扩展。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.common import ok
from app.core.errors import BadRequestError, ConflictError
from app.deps import get_registry
from app.models.schemas import WriteRequest, WriteResult
from app.services.registry import Registry

router = APIRouter(prefix="/api/agents", tags=["files"])

VALID_ROLES = {"CORE", "MEMORY", "SKILL", "META", "OTHER"}


class CrossWriteItem(BaseModel):
    agent_id: str
    path: str


class CrossWriteRequest(BaseModel):
    files: list[CrossWriteItem] = Field(..., description="要写入的 (agent, path) 列表")
    content: str = Field(..., description="统一写入的内容")


@router.get("/{agent_id}/files")
def list_files(agent_id: str, role: str | None = Query(None), reg: Registry = Depends(get_registry)):
    """列出 Agent 的 Prompt Pack 文件（可 role 过滤）。"""
    if role is not None and role not in VALID_ROLES:
        raise BadRequestError(f"非法 role：{role}，可选 {sorted(VALID_ROLES)}")
    files = reg.file_manager.list(agent_id)
    if role:
        files = [f for f in files if f.role == role]
    return ok([f.model_dump() for f in files])


@router.get("/{agent_id}/files/{path:path}/history")
def file_history(agent_id: str, path: str, reg: Registry = Depends(get_registry)):
    """文件备份历史（按时间倒序）。注意：必须先于 /{path:path} 注册。"""
    reg.file_manager.require_agent(agent_id)
    history = reg.backup.list_history(agent_id, path)
    return ok([b.model_dump() for b in history])


@router.get("/{agent_id}/files/{path:path}")
def read_file(agent_id: str, path: str, reg: Registry = Depends(get_registry)):
    """读取文件内容（read-only）。"""
    content = reg.file_manager.read(agent_id, path)
    return ok(content.model_dump())


@router.put("/{agent_id}/files/{path:path}")
def write_file(agent_id: str, path: str, body: WriteRequest, reg: Registry = Depends(get_registry)):
    """写入文件（自动备份 + 乐观锁 + lint 严格模式校验）。"""
    # lint 严格模式：违规阻止保存
    if reg.config.lint.strict_mode:
        warnings = reg.lint.lint_file(agent_id, path, body.content)
        if warnings:
            raise ConflictError(
                "lint 严格模式：存在违规，已阻止保存",
                details={"warnings": [w.model_dump() for w in warnings]},
            )
    result: WriteResult = reg.file_manager.write(agent_id, path, body.content,
                                                 expected_sha256=body.expected_sha256)
    warnings = reg.lint.lint_file(agent_id, path, body.content, result.size_bytes)
    result.lint_warnings = len(warnings)
    with reg.db.session() as s:
        from app.models.db import FileRow

        row = s.query(FileRow).filter(FileRow.agent_id == agent_id, FileRow.path == path).first()
        if row:
            row.lint_warnings = len(warnings)
            s.commit()
    return ok(result.model_dump())


@router.delete("/{agent_id}/files/{path:path}")
def delete_file(agent_id: str, path: str, reg: Registry = Depends(get_registry)):
    """删除文件（走回收站，可恢复）。"""
    reg.file_manager.delete(agent_id, path)
    return ok({"agent_id": agent_id, "path": path, "deleted": True})


@router.post("/files/cross-write")
def cross_write(body: CrossWriteRequest, reg: Registry = Depends(get_registry)):
    """跨 Agent 编辑：同一内容写入多个 Agent，每个 Agent 独立备份。"""
    results = []
    for item in body.files:
        result = reg.file_manager.write(item.agent_id, item.path, body.content)
        results.append({"agent_id": item.agent_id, "path": item.path, "backup_id": result.backup_id})
    return ok({"results": results, "agents": len(body.files)})
