"""ImportExportService：Prompt Pack 导出 / 导入（.tar.gz + MANIFEST.json + sha256 校验）。

安全（见 docs/SECURITY.md）：safe_extract 防 tar bomb；冲突默认 skip；绝不默认覆盖。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.config import Config
from app.core.errors import ManifestCorruptedError, UploadNotFoundError
from app.core.security import safe_extract
from app.models.schemas import (
    ConflictItem,
    ImportExecuteResult,
    ImportPreviewResult,
    ImportResultItem,
    Manifest,
    ManifestFile,
)
from app.services.agent_discovery import AgentDiscovery
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.file_manager import FileManager

UPLOAD_TTL_SECONDS = 30 * 60


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
        self.uploads: dict[str, tuple[float, Path]] = {}

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

    # ---------- 导入 ----------

    def _store_upload(self, data: bytes) -> str:
        self.config.uploads_dir.mkdir(parents=True, exist_ok=True)
        upload_id = str(uuid.uuid4())
        path = self.config.uploads_dir / f"{upload_id}.tar.gz"
        path.write_bytes(data)
        self._cleanup_expired_uploads()
        self.uploads[upload_id] = (time.time(), path)
        return upload_id

    def _cleanup_expired_uploads(self) -> None:
        now = time.time()
        for uid, (ts, path) in list(self.uploads.items()):
            if now - ts > UPLOAD_TTL_SECONDS:
                path.unlink(missing_ok=True)
                self.uploads.pop(uid, None)

    def _get_upload(self, upload_id: str) -> Path:
        entry = self.uploads.get(upload_id)
        if entry is None:
            raise UploadNotFoundError(f"上传不存在或已过期：{upload_id}", details={"upload_id": upload_id})
        ts, path = entry
        if time.time() - ts > UPLOAD_TTL_SECONDS:
            raise UploadNotFoundError(f"上传已过期，请重新上传：{upload_id}", details={"upload_id": upload_id})
        return path

    def _extract(self, tarball: Path) -> Path:
        extract_dir = Path(tempfile.mkdtemp(prefix="soulforge-import-"))
        with tarfile.open(tarball, "r:gz") as tf:
            safe_extract(tf, extract_dir)
        return extract_dir

    def _load_manifest(self, extract_dir: Path) -> Manifest:
        manifest_path = extract_dir / "MANIFEST.json"
        if not manifest_path.is_file():
            raise ManifestCorruptedError("导入包缺少 MANIFEST.json")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ManifestCorruptedError("MANIFEST.json 解析失败")
        # 校验 sha256（防篡改）
        files = []
        for item in raw.get("files", []):
            fpath = item["path"]
            f = extract_dir / fpath
            if not f.is_file():
                raise ManifestCorruptedError(f"manifest 声明了文件但包内缺失：{fpath}")
            actual = sha256_of(f)
            if actual != item.get("sha256"):
                raise ManifestCorruptedError(f"sha256 校验失败：{fpath}")
            files.append(ManifestFile(path=fpath, size=item.get("size", 0), sha256=actual))
        return Manifest(
            soulforge_version=raw.get("soulforge_version", ""),
            export_time=raw.get("export_time", ""),
            agent_id=raw.get("agent_id", ""),
            files=files,
        )

    def preview(self, data: bytes, target_agent_id: str) -> ImportPreviewResult:
        upload_id = self._store_upload(data)
        extract_dir = self._extract(self._get_upload(upload_id))
        try:
            manifest = self._load_manifest(extract_dir)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
        agent = self.discovery.require(target_agent_id)
        root = Path(agent.workspace)
        conflicts = []
        for mf in manifest.files:
            target = root / mf.path
            conflicts.append(ConflictItem(
                path=mf.path,
                exists_in_target=target.is_file(),
                target_size=target.stat().st_size if target.is_file() else None,
            ))
        return ImportPreviewResult(upload_id=upload_id, target_agent_id=target_agent_id, manifest=manifest, conflicts=conflicts)

    def execute(self, upload_id: str, target_agent_id: str, conflicts: dict[str, str]) -> ImportExecuteResult:
        tarball = self._get_upload(upload_id)
        extract_dir = self._extract(tarball)
        try:
            manifest = self._load_manifest(extract_dir)
            agent = self.discovery.require(target_agent_id)
            root = Path(agent.workspace)
            results: list[ImportResultItem] = []
            for mf in manifest.files:
                src = extract_dir / mf.path
                target = root / mf.path
                exists = target.is_file()
                strategy = conflicts.get(mf.path, "skip") if exists else "add"
                if strategy == "skip":
                    results.append(ImportResultItem(file=mf.path, action="skipped"))
                    continue
                if strategy == "merge":
                    merged = self._merge_files(target, src)
                    self.file_manager.write(target_agent_id, mf.path, merged, audit=False)
                    self.audit.record("import", target_agent_id, mf.path, {"strategy": "merge", "upload_id": upload_id})
                    results.append(ImportResultItem(file=mf.path, action="merged"))
                elif strategy == "overwrite":
                    self.file_manager.write(target_agent_id, mf.path, src.read_text(encoding="utf-8", errors="replace"), audit=False)
                    self.audit.record("import", target_agent_id, mf.path, {"strategy": "overwrite", "upload_id": upload_id})
                    results.append(ImportResultItem(file=mf.path, action="overwritten"))
                else:  # add（目标不存在）
                    self.file_manager.write(target_agent_id, mf.path, src.read_text(encoding="utf-8", errors="replace"), audit=False)
                    self.audit.record("import", target_agent_id, mf.path, {"strategy": "add", "upload_id": upload_id})
                    results.append(ImportResultItem(file=mf.path, action="added"))
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
        return ImportExecuteResult(manifest=manifest, results=results)

    def _merge_files(self, target: Path, src: Path) -> str:
        """简单行级合并（best-effort）：导入内容为底，补上目标独有的行。"""
        target_lines = target.read_text(encoding="utf-8", errors="replace").splitlines() if target.is_file() else []
        src_lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        seen = set(src_lines)
        merged = list(src_lines)
        for line in target_lines:
            if line not in seen:
                merged.append(line)
                seen.add(line)
        return "\n".join(merged)
