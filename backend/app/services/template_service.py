"""TemplateService：内置模板系统（standard / minimal / lawyer-agent / writer-agent）。"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.errors import TemplateNotFoundError
from app.models.schemas import TemplateApplyResult, TemplateInfo
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService

# 模板目录在项目根（soulforge/templates/），位于 backend/app/services 上溯 4 级
TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "templates"

NAME_MAP = {
    "standard": "Standard",
    "minimal": "Minimal",
    "lawyer-agent": "Lawyer Agent",
    "writer-agent": "Writer Agent",
}
DESC_MAP = {
    "standard": "标准配置（含全部 CORE 文件 + SOUL.md 示例）",
    "minimal": "极简（仅 AGENTS.md + IDENTITY.md）",
    "lawyer-agent": "律师专用（法答 / IMA 知识库偏好）",
    "writer-agent": "作家专用（小说 / 公众号）",
}


class TemplateService:
    def __init__(self, backup: BackupService, audit: AuditService):
        self.backup = backup
        self.audit = audit

    def _template_dir(self, template_id: str) -> Path:
        d = TEMPLATES_ROOT / template_id
        if not d.is_dir():
            raise TemplateNotFoundError(f"模板不存在：{template_id}", details={"template_id": template_id})
        return d

    def list_templates(self) -> list[TemplateInfo]:
        out = []
        if not TEMPLATES_ROOT.is_dir():
            return out
        for d in sorted(TEMPLATES_ROOT.iterdir()):
            if not d.is_dir():
                continue
            count = len([p for p in d.rglob("*.md")])
            out.append(TemplateInfo(
                id=d.name,
                name=NAME_MAP.get(d.name, d.name),
                description=DESC_MAP.get(d.name, ""),
                file_count=count,
            ))
        return out

    def apply(self, template_id: str, new_agent_id: str, target_workspace: str) -> TemplateApplyResult:
        src = self._template_dir(template_id)
        ws = Path(target_workspace).expanduser()
        ws.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        for f in sorted(src.rglob("*.md")):
            rel = f.relative_to(src)
            dest = ws / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_file():
                self.backup.backup(new_agent_id, rel.as_posix(), dest, reason="pre-template")
            shutil.copy2(f, dest)
            files_created.append(rel.as_posix())
        self.audit.record("template-apply", new_agent_id, None,
                          {"template_id": template_id, "workspace": str(ws)})
        return TemplateApplyResult(agent_id=new_agent_id, workspace=str(ws), files_created=files_created)
