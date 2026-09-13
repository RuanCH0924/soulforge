"""ImportExportService：Prompt Pack 导出（.tar.gz + MANIFEST.json）。

说明：类名保留历史命名，当前仅提供「导出」能力（导入功能已移除）。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import Config
from app.models.schemas import Manifest, ManifestFile
from app.services.agent_discovery import AgentDiscovery
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.file_manager import FileManager


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ImportExportService:
    def __init__(self, config: Config, discovery: AgentDiscovery, file_manager: FileManager,
                 backup: BackupService, audit: AuditService):
        self.config = config
        self.discovery = discovery
        self.file_manager = file_manager
        self.backup = backup
        self.audit = audit

    # ---------- 导出 ----------

    def export_agent(self, agent_id: str) -> Path:
        agent = self.discovery.require(agent_id)
        files = self.file_manager.list(agent_id)
        tmp = Path(tempfile.mkdtemp(prefix="soulforge-export-"))
        for f in files:
            src = Path(agent.workspace) / f.path
            dst = tmp / f.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        manifest_files = [
            ManifestFile(path=f.path, size=f.size_bytes, sha256=sha256_of(Path(agent.workspace) / f.path))
            for f in files
        ]
        manifest = Manifest(
            soulforge_version="0.1.0",
            export_time=datetime.now().isoformat(),
            agent_id=agent_id,
            files=manifest_files,
        )
        (tmp / "MANIFEST.json").write_text(json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        out = Path(tempfile.mkdtemp(prefix="soulforge-export-out-")) / f"soulforge-{agent_id}-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
        shutil.make_archive(str(out).removesuffix(".tar.gz"), "gztar", tmp)
        self.audit.record("export", agent_id, None, {"files": len(files)})
        return out

    def export_all(self) -> Path:
        agents = self.discovery.discover()
        tmp = Path(tempfile.mkdtemp(prefix="soulforge-export-all-"))
        all_agents = []
        for a in agents:
            files = self.file_manager.list(a.id)
            agent_dir = tmp / a.id
            for f in files:
                src = Path(a.workspace) / f.path
                dst = agent_dir / f.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            all_agents.append({
                "agent_id": a.id,
                "files": [{"path": f.path, "size": f.size_bytes, "sha256": sha256_of(Path(a.workspace) / f.path)} for f in files],
            })
        root_manifest = {
            "soulforge_version": "0.1.0",
            "export_time": datetime.now().isoformat(),
            "export_all": True,
            "agents": all_agents,
        }
        (tmp / "MANIFEST.json").write_text(json.dumps(root_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        out = Path(tempfile.mkdtemp(prefix="soulforge-export-all-out-")) / f"soulforge-all-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
        shutil.make_archive(str(out).removesuffix(".tar.gz"), "gztar", tmp)
        self.audit.record("export", None, None, {"agents": len(agents)})
        return out
