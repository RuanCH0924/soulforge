"""路由：AI 自动整理（M13 · Phase 2.5 Step 3）。

端点见 docs/API.md §3.13。AI 输出绝不直接覆盖原文件，必须经老板 diff 确认。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import AIJobCreate, AIRegenerateRequest
from app.services.registry import Registry

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/jobs", status_code=202)
async def create_job(body: AIJobCreate, reg: Registry = Depends(get_registry)):
    """创建 AI 整理任务（异步执行，立即返回 pending）。"""
    result = await reg.ai_jobs.create(
        body.agent_id, body.file_path, body.preset_id, body.provider_id, body.extra_instructions)
    return ok(result.model_dump())


@router.get("/jobs")
def list_jobs(agent_id: str | None = Query(None), status: str | None = Query(None),
              limit: int = Query(50, ge=1, le=200), reg: Registry = Depends(get_registry)):
    """列出 AI 任务历史（按时间倒序）。"""
    return ok([j.model_dump() for j in reg.ai_jobs.list(agent_id, status, limit)])


@router.get("/jobs/{job_id}")
def get_job(job_id: str, reg: Registry = Depends(get_registry)):
    """查询任务状态与结果。"""
    return ok(reg.ai_jobs.get(job_id).model_dump())


@router.post("/jobs/{job_id}/apply")
def apply_job(job_id: str, reg: Registry = Depends(get_registry)):
    """应用 AI 输出（写入文件 + 自动备份 + 审计）。"""
    return ok(reg.ai_jobs.apply(job_id).model_dump())


@router.post("/jobs/{job_id}/reject")
def reject_job(job_id: str, reg: Registry = Depends(get_registry)):
    """拒绝 AI 输出（不写入）。"""
    return ok(reg.ai_jobs.reject(job_id).model_dump())


@router.post("/jobs/{job_id}/regenerate", status_code=202)
async def regenerate_job(job_id: str, body: AIRegenerateRequest, reg: Registry = Depends(get_registry)):
    """重新生成（带新指令）：旧 job 标记 superseded，新建 pending 任务。"""
    result = await reg.ai_jobs.regenerate(job_id, body.extra_instructions)
    return ok(result.model_dump())
