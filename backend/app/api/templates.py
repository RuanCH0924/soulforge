"""路由：模板系统（M9）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import TemplateApplyRequest
from app.services.registry import Registry

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates(reg: Registry = Depends(get_registry)):
    """列出内置模板。"""
    templates = reg.templates.list_templates()
    return ok([t.model_dump() for t in templates])


@router.post("/apply")
def apply_template(body: TemplateApplyRequest, reg: Registry = Depends(get_registry)):
    """应用模板创建新 Agent（生成 Prompt Pack 到目标 workspace）。"""
    result = reg.templates.apply(body.template_id, body.new_agent_id, body.target_workspace)
    return ok(result.model_dump())
