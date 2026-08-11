"""路由：Diff 对比（M4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api/diff", tags=["diff"])


@router.get("")
def diff_agents(a: str = Query(..., description="Agent A id"),
                b: str = Query(..., description="Agent B id"),
                file: str = Query(..., description="文件路径"),
                reg: Registry = Depends(get_registry)):
    """对比两个 Agent 的同名文件。"""
    result = reg.diff.diff_agents(a, b, file)
    return ok(result.model_dump())


@router.get("/history")
def diff_history(agent: str = Query(...), file: str = Query(...),
                 against: int = Query(..., description="备份 ID"),
                 reg: Registry = Depends(get_registry)):
    """对比当前文件 vs 历史备份。"""
    result = reg.diff.diff_history(agent, file, against)
    return ok(result.model_dump())
