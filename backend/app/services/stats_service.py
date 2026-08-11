"""StatsService：首页仪表盘统计。"""
from __future__ import annotations

from app.config import Config
from app.models.db import AgentRow, BackupRow, Database, FileRow
from app.models.schemas import StatsResult
from app.services.agent_discovery import AgentDiscovery


class StatsService:
    def __init__(self, config: Config, db: Database, discovery: AgentDiscovery):
        self.config = config
        self.db = db
        self.discovery = discovery

    def get_stats(self) -> StatsResult:
        with self.db.session() as s:
            files = s.query(FileRow).all()
            backups = s.query(BackupRow).all()
            last_scan = s.query(AgentRow).filter(AgentRow.last_scanned_at.isnot(None)).order_by(
                AgentRow.last_scanned_at.desc()).first()
        agents_total = len(self.discovery.discover())
        files_total = len(files)
        core_files = sum(1 for f in files if f.role == "CORE")
        memory_files = sum(1 for f in files if f.role == "MEMORY")
        backup_total = len(backups)
        backup_size_bytes = sum(b.size_bytes for b in backups)
        lint_warnings_total = sum(f.lint_warnings or 0 for f in files)
        disk_usage_bytes = sum(f.size_bytes for f in files)
        return StatsResult(
            agents_total=agents_total,
            files_total=files_total,
            core_files=core_files,
            memory_files=memory_files,
            backup_total=backup_total,
            backup_size_bytes=backup_size_bytes,
            lint_warnings_total=lint_warnings_total,
            last_scan_at=last_scan.last_scanned_at if last_scan else None,
            disk_usage_bytes=disk_usage_bytes,
        )
