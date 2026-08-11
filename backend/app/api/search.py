"""路由：跨 Agent 搜索（M3）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.common import ok
from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="搜索词 / 正则")
    agent_ids: list[str] | None = Field(None, description="限定 Agent，不传 = 全部")
    file_patterns: list[str] | None = Field(None, description="限定文件（glob 模式，如 SOUL.md）")
    regex: bool = False
    case_sensitive: bool = True
    context_lines: int = Field(3, ge=0, le=10)
    limit: int = Field(100, ge=1, le=500)


@router.post("")
def search(body: SearchRequest, reg: Registry = Depends(get_registry)):
    """跨 Agent 全文搜索（ripgrep，fallback 到 Python）。"""
    result = reg.search.search(
        body.query,
        agent_ids=body.agent_ids,
        file_patterns=body.file_patterns,
        regex=body.regex,
        case_sensitive=body.case_sensitive,
        context_lines=body.context_lines,
        limit=body.limit,
    )
    return ok(result.model_dump())
