"""路由：工作日志总结（记忆归纳，M16）。

端点见 docs/API.md §3.16。核心约束与日志标准化一致：**计划与写入分离**，
执行必须由人看过 diff 后确认；未确认前不写盘、不动任何源文件。
清理源文件是汇总写入后单独触发的可选动作。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import SummaryRunCreate
from app.services.registry import Registry

router = APIRouter(prefix="/api/summary-runs", tags=["summary"])


@router.post("", status_code=202)
async def create_run(body: SummaryRunCreate, reg: Registry = Depends(get_registry)):
    """创建归纳批次（异步生成计划，立即返回 planned）。

    命中幂等键（同 Agent / 范围 / 预设版本 / provider / 来源与目标内容）时直接复用既有批次，
    不产生第二次 LLM 调用。
    """
    return ok((await reg.summary.create(body)).model_dump())


@router.get("")
def list_runs(agent_id: str | None = Query(None), status: str | None = Query(None),
              limit: int = Query(50, ge=1, le=200), reg: Registry = Depends(get_registry)):
    """列出归纳批次历史（按时间倒序）。"""
    return ok([r.model_dump() for r in reg.summary.list(agent_id, status, limit)])


@router.get("/{run_id}")
def get_run(run_id: str, reg: Registry = Depends(get_registry)):
    """批次详情（含来源清单、产物正文、diff 与强规则报告）。"""
    return ok(reg.summary.get(run_id).model_dump())


@router.post("/{run_id}/apply")
def apply_run(run_id: str, reg: Registry = Depends(get_registry)):
    """确认写入汇总文件：写前验收 + 乐观锁 → 写入（自动备份 + 审计）→ 验收。

    源文件默认不动；如需清理源文件请另行调用 `cleanup-sources`。
    """
    return ok(reg.summary.apply(run_id).model_dump())


@router.post("/{run_id}/reject")
def reject_run(run_id: str, reg: Registry = Depends(get_registry)):
    """拒绝批次（不写入任何文件）。"""
    return ok(reg.summary.reject(run_id).model_dump())


@router.post("/{run_id}/cleanup-sources")
def cleanup_sources(run_id: str, reg: Registry = Depends(get_registry)):
    """清理该批次范围内的源文件（移入系统回收站，可恢复）。

    仅在汇总文件已写入后可调用；产物自身永不删除。
    """
    return ok(reg.summary.cleanup_sources(run_id).model_dump())


@router.get("/{run_id}/report")
def run_report(run_id: str, reg: Registry = Depends(get_registry)):
    """验收报告（对磁盘上的真实文件核对，只读、可重复跑）。"""
    return ok(reg.summary.build_report(run_id).model_dump())
