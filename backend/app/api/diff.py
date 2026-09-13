"""路由：Diff 对比（M4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.deps import get_registry
from app.services.diff_service import MODE_IGNORE_WHITESPACE, VALID_MODES
from app.services.registry import Registry

router = APIRouter(prefix="/api/diff", tags=["diff"])

MODE_QUERY = Query(
    MODE_IGNORE_WHITESPACE,
    description="归一化口径：ignore_whitespace（默认，忽略空白/空行/零宽字符等格式噪声）"
                " 或 strict（仅忽略 BOM/换行风格/零宽字符）",
)


def _checked_mode(mode: str) -> str:
    """非法口径回落到默认值，避免前端传参错误导致 500。"""
    return mode if mode in VALID_MODES else MODE_IGNORE_WHITESPACE


@router.get("")
def diff_agents(a: str = Query(..., description="Agent A id"),
                b: str = Query(..., description="Agent B id"),
                file: str = Query(..., description="文件路径"),
                mode: str = MODE_QUERY,
                reg: Registry = Depends(get_registry)):
    """对比两个 Agent 的同名文件。"""
    result = reg.diff.diff_agents(a, b, file, mode=_checked_mode(mode))
    return ok(result.model_dump())


@router.get("/history")
def diff_history(agent: str = Query(...), file: str = Query(...),
                 against: int = Query(..., description="备份 ID"),
                 mode: str = MODE_QUERY,
                 reg: Registry = Depends(get_registry)):
    """对比当前文件 vs 历史备份。"""
    result = reg.diff.diff_history(agent, file, against, mode=_checked_mode(mode))
    return ok(result.model_dump())
