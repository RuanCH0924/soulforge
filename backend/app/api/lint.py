"""路由：健康检查 / Lint（M8）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import ok
from app.deps import get_registry
from app.services.registry import Registry

router = APIRouter(prefix="/api/lint", tags=["lint"])


@router.get("/all")
def lint_all(reg: Registry = Depends(get_registry)):
    """对全部 Agent 跑 lint。"""
    agents = reg.discovery.discover()
    results = []
    for a in agents:
        r = reg.lint.lint_agent(a.id, reg.file_manager)
        results.append(r.model_dump())
    return ok({"results": results, "agents": len(results)})


@router.get("/rules")
def lint_rules(reg: Registry = Depends(get_registry)):
    """列出全部 lint 规则（供 UI 展示「在检查什么」）。

    注意：必须声明在 `/{agent_id}` 之前，否则会被当成 agent_id 吃掉。
    """
    rules = reg.lint.rule_catalog()
    return ok({"rules": [r.model_dump() for r in rules], "count": len(rules)})


@router.get("/{agent_id}")
def lint_agent(agent_id: str, reg: Registry = Depends(get_registry)):
    """对单个 Agent 跑 lint。"""
    reg.discovery.require(agent_id)
    result = reg.lint.lint_agent(agent_id, reg.file_manager)
    return ok(result.model_dump())


@router.get("/file/{agent_id}/{file_path:path}")
def lint_file(agent_id: str, file_path: str, reg: Registry = Depends(get_registry)):
    """对单文件 lint。"""
    content = reg.file_manager.read(agent_id, file_path)
    warnings = reg.lint.lint_file(agent_id, file_path, content.content, content.size_bytes)
    return ok({"agent_id": agent_id, "file_path": file_path, "warnings": [w.model_dump() for w in warnings]})
