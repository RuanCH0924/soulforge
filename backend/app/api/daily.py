"""路由：工作日志标准化批次（M15 · P2）。

端点见 docs/API.md §3.15。核心约束与 AI 整理一致：**计划与写入分离**，
执行必须由人逐个 diff 确认；未确认前不写盘、不删碎片。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import (
    DailyRunApplyRequest,
    DailyRunCreate,
    DailyRunSkipRequest,
)
from app.services.registry import Registry

router = APIRouter(prefix="/api/daily-runs", tags=["daily"])


@router.post("", status_code=202)
async def create_run(body: DailyRunCreate, reg: Registry = Depends(get_registry)):
    """创建批次（异步逐日生成计划，立即返回 planned）。

    命中幂等键（同 Agent / 范围 / 预设 / provider / 来源内容）时直接复用既有批次，
    不产生第二次 LLM 调用。
    """
    return ok((await reg.daily_runs.create(body)).model_dump())


@router.get("")
def list_runs(agent_id: str | None = Query(None), status: str | None = Query(None),
              limit: int = Query(50, ge=1, le=200), reg: Registry = Depends(get_registry)):
    """列出批次历史（按时间倒序）。"""
    return ok([r.model_dump() for r in reg.daily_runs.list(agent_id, status, limit)])


@router.get("/{run_id}")
def get_run(run_id: str, reg: Registry = Depends(get_registry)):
    """批次详情（含逐日条目的来源、diff、强规则报告与状态）。"""
    return ok(reg.daily_runs.get(run_id).model_dump())


@router.post("/{run_id}/apply")
def apply_run(run_id: str, body: DailyRunApplyRequest, reg: Registry = Depends(get_registry)):
    """应用选中的日期：写前验收 + 乐观锁 → 写入（自动备份 + 审计）→ 删除碎片 → 验收。"""
    return ok(reg.daily_runs.apply(run_id, body).model_dump())


@router.post("/{run_id}/reject")
def reject_run(run_id: str, reg: Registry = Depends(get_registry)):
    """拒绝批次（不写入任何文件）。"""
    return ok(reg.daily_runs.reject(run_id).model_dump())


@router.post("/{run_id}/skip")
def skip_days(run_id: str, body: DailyRunSkipRequest, reg: Registry = Depends(get_registry)):
    """跳过若干日（人工决策，不改写这些日）。"""
    return ok(reg.daily_runs.skip(run_id, body.dates).model_dump())


@router.get("/{run_id}/report")
def run_report(run_id: str, reg: Registry = Depends(get_registry)):
    """验收报告（对磁盘上的真实文件核对，只读、可重复跑）。"""
    return ok(reg.daily_runs.build_report(run_id).model_dump())
