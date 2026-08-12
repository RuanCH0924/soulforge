"""路由：文档预设系统（M11 · Phase 2.5 Step 1）。

端点见 docs/API.md §3.11。应用预设走 plan + execute 两步，绝不直接覆盖。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.common import ok
from app.core.errors import BadRequestError
from app.deps import get_registry
from app.models.schemas import (
    PresetApplyExecuteRequest,
    PresetApplyRequest,
    PresetCreate,
    PresetUpdate,
    PresetTargetType,
)
from app.services.registry import Registry

router = APIRouter(prefix="/api/presets", tags=["presets"])

VALID_TARGET_TYPES = set(PresetTargetType.__args__)


@router.get("")
def list_presets(target_file_type: str | None = Query(None), reg: Registry = Depends(get_registry)):
    """列出全部预设（系统 + 用户），可按适用文件类型过滤。"""
    if target_file_type is not None and target_file_type not in VALID_TARGET_TYPES:
        raise BadRequestError(
            f"非法 target_file_type：{target_file_type}，可选 {sorted(VALID_TARGET_TYPES)}")
    return ok([p.model_dump() for p in reg.presets.list(target_file_type)])


@router.post("", status_code=201)
def create_preset(body: PresetCreate, reg: Registry = Depends(get_registry)):
    """创建用户预设（is_system=false，version=1）。"""
    return ok(reg.presets.create(body).model_dump())


@router.get("/{preset_id}")
def get_preset(preset_id: str, reg: Registry = Depends(get_registry)):
    """查看预设完整内容（含 sections / frontmatter / style_rules）。"""
    return ok(reg.presets.get(preset_id).model_dump())


@router.put("/{preset_id}")
def update_preset(preset_id: str, body: PresetUpdate, reg: Registry = Depends(get_registry)):
    """编辑预设（version 自增 +1）。系统预设仅允许改 description + style_rules。"""
    return ok(reg.presets.update(preset_id, body).model_dump())


@router.delete("/{preset_id}")
def delete_preset(preset_id: str, reg: Registry = Depends(get_registry)):
    """删除用户预设；系统预设 → 403。"""
    reg.presets.delete(preset_id)
    return ok({"id": preset_id, "deleted": True})


@router.get("/{preset_id}/versions")
def list_preset_versions(preset_id: str, reg: Registry = Depends(get_registry)):
    """查看预设版本历史（按版本倒序，含快照）。"""
    return ok([v.model_dump() for v in reg.presets.list_versions(preset_id)])


@router.post("/{preset_id}/versions/{version_id}/restore")
def restore_preset_version(preset_id: str, version_id: int, reg: Registry = Depends(get_registry)):
    """回溯到指定版本：应用历史快照，version +1 并保存新快照。"""
    return ok(reg.presets.restore_version(preset_id, version_id).model_dump())


@router.post("/{preset_id}/apply")
def apply_preset(preset_id: str, body: PresetApplyRequest, reg: Registry = Depends(get_registry)):
    """应用预设到指定 Agent + 文件，生成 diff plan（不写入文件）。"""
    plan = reg.presets.apply_plan(preset_id, body.agent_id, body.file_path, body.extra_instructions)
    return ok(plan.model_dump())


@router.post("/{preset_id}/apply/execute")
def apply_preset_execute(preset_id: str, body: PresetApplyExecuteRequest,
                         reg: Registry = Depends(get_registry)):
    """执行应用（写入文件 + 自动备份 + 审计）。"""
    result = reg.presets.apply_execute(body.plan_id, body.agent_id, body.file_path)
    return ok(result.model_dump())
