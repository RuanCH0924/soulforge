"""BackupService：自动备份 / 历史 / 回滚支持 / 保留策略。

备份物理路径：{data_dir}/backups/{agent_id}/{sanitized_path}/{filename}.{YYYYMMDD-HHMMSS}.bak
"""
from __future__ import annotations

import hashlib
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.config import Config
from app.core.errors import FileNotFoundError
from app.models.db import BackupRow, Database
from app.models.schemas import BackupEntry


class BackupService:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.root = config.backups_dir

    def _backup_path(self, agent_id: str, file_path: str, source: Path) -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        sanitized = file_path.replace("/", "_")
        base = self.root / agent_id / sanitized
        base.mkdir(parents=True, exist_ok=True)
        candidate = base / f"{source.name}.{ts}.bak"
        # 同一秒内多次备份会撞名：追加序号保证唯一（主格式保持 YYYYMMDD-HHMMSS）
        n = 1
        while candidate.exists():
            candidate = base / f"{source.name}.{ts}-{n}.bak"
            n += 1
        return candidate

    def backup(self, agent_id: str, file_path: str, source: Path, *, reason: str = "manual") -> int | None:
        """把 source 文件复制为备份，返回 backup_id。新文件（不存在）返回 None。"""
        if not source.is_file():
            return None
        backup_path = self._backup_path(agent_id, file_path, source)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
        sha = hashlib.sha256(backup_path.read_bytes()).hexdigest()
        size = backup_path.stat().st_size
        with self.db.session() as s:
            row = BackupRow(
                agent_id=agent_id,
                file_path=file_path,
                backup_path=str(backup_path),
                reason=reason,
                sha256=sha,
                size_bytes=size,
            )
            s.add(row)
            s.commit()
            return row.id

    def list_history(self, agent_id: str, file_path: str) -> list[BackupEntry]:
        with self.db.session() as s:
            rows = (
                s.query(BackupRow)
                .filter(BackupRow.agent_id == agent_id, BackupRow.file_path == file_path)
                .order_by(BackupRow.created_at.desc(), BackupRow.id.desc())
                .all()
            )
            return [BackupEntry(backup_id=r.id, reason=r.reason, size_bytes=r.size_bytes, sha256=r.sha256, created_at=r.created_at) for r in rows]

    def list_for_agent(self, agent_id: str) -> list[tuple[str, list[BackupEntry]]]:
        with self.db.session() as s:
            rows = s.query(BackupRow).filter(BackupRow.agent_id == agent_id).order_by(BackupRow.created_at.desc()).all()
        grouped: dict[str, list[BackupEntry]] = {}
        for r in rows:
            grouped.setdefault(r.file_path, []).append(
                BackupEntry(backup_id=r.id, reason=r.reason, size_bytes=r.size_bytes, sha256=r.sha256, created_at=r.created_at)
            )
        return list(grouped.items())

    def get(self, backup_id: int) -> BackupRow | None:
        with self.db.session() as s:
            return s.get(BackupRow, backup_id)

    def read_content(self, backup_id: int) -> str:
        row = self.get(backup_id)
        if row is None:
            raise FileNotFoundError(f"备份不存在：{backup_id}", details={"backup_id": backup_id})
        path = Path(row.backup_path)
        if not path.is_file():
            raise FileNotFoundError(f"备份文件缺失：{row.backup_path}", details={"backup_id": backup_id})
        return path.read_text(encoding="utf-8", errors="replace")

    def cleanup_old(self) -> int:
        """删除超过保留期的备份（物理文件 + 数据库记录）。"""
        retention_days = self.config.backup.retention_days
        cutoff = int((datetime.now() - timedelta(days=retention_days)).timestamp())
        removed = 0
        with self.db.session() as s:
            rows = s.query(BackupRow).filter(BackupRow.created_at < cutoff).all()
            for r in rows:
                try:
                    Path(r.backup_path).unlink(missing_ok=True)
                except OSError:
                    pass
                s.delete(r)
                removed += 1
            s.commit()
        return removed
