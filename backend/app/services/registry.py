"""服务装配：把所有服务接线成一个 Registry，供 FastAPI 依赖注入。"""
from __future__ import annotations

import time

from loguru import logger

from app.config import Config
from app.models.db import Database
from app.services.agent_discovery import AgentDiscovery
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.diff_service import DiffService
from app.services.file_manager import FileManager
from app.services.import_export import ImportExportService
from app.services.lint_service import LintService
from app.services.search_service import SearchService
from app.services.stats_service import StatsService
from app.services.sync_service import SyncService
from app.services.template_service import TemplateService


class Registry:
    def __init__(self, config: Config):
        self.config = config
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.uploads_dir.mkdir(parents=True, exist_ok=True)

        self.db = Database(config.db_path)
        self.db.init_db()

        self.audit = AuditService(self.db)
        self.discovery = AgentDiscovery(config)
        self.backup = BackupService(config, self.db)
        self.file_manager = FileManager(config, self.db, self.discovery, self.backup, self.audit)
        self.lint = LintService(config)
        self.search = SearchService(config, self.discovery, self.file_manager)
        self.diff = DiffService(self.file_manager, self.backup)
        self.sync = SyncService(self.file_manager, self.backup, self.audit)
        self.import_export = ImportExportService(config, self.discovery, self.file_manager, self.backup, self.audit)
        self.templates = TemplateService(self.backup, self.audit)
        self.stats = StatsService(config, self.db, self.discovery)

    def startup(self) -> None:
        """启动流程：清理过期备份 + 重建索引。"""
        t0 = time.time()
        removed = self.backup.cleanup_old()
        if removed:
            self.db.vacuum()
        scan = self.file_manager.scan_all()
        logger.info(
            "启动完成：清理备份 {} 个，扫描 {} 个 Agent / {} 个文件（{:.0f}ms）",
            removed, scan.agents_scanned, scan.files_indexed, (time.time() - t0) * 1000,
        )

    # ---------- 配置中心（config.toml 可视化，v1.0 项） ----------

    def get_config_dict(self) -> dict:
        """返回当前生效配置（供前端展示）。"""
        c = self.config
        return {
            "server": {"host": c.server.host, "port": c.server.port},
            "backup": {
                "retention_days": c.backup.retention_days,
                "auto_backup_on_write": c.backup.auto_backup_on_write,
            },
            "lint": {"enabled": c.lint.enabled, "strict_mode": c.lint.strict_mode},
            "ui": {"default_theme": c.ui.default_theme, "default_view": c.ui.default_view},
            "advanced": {
                "show_skills": c.advanced.show_skills,
                "show_meta": c.advanced.show_meta,
                "show_memory": c.advanced.show_memory,
                "show_other": c.advanced.show_other,
            },
            "openclaw": {"dir": str(c.openclaw_dir)},
        }

    def update_config(self, patch: dict) -> dict:
        """局部更新配置：合并进 config.toml + 立即生效（host/port 需重启）。

        patch 形如 {"lint": {"strict_mode": true}, ...}，各字段已过 Pydantic 校验。
        """
        c = self.config
        if "server" in patch:
            if "host" in patch["server"]:
                c.server.host = patch["server"]["host"]
            if "port" in patch["server"]:
                c.server.port = patch["server"]["port"]
        if "backup" in patch:
            if "retention_days" in patch["backup"]:
                c.backup.retention_days = patch["backup"]["retention_days"]
            if "auto_backup_on_write" in patch["backup"]:
                c.backup.auto_backup_on_write = patch["backup"]["auto_backup_on_write"]
        if "lint" in patch:
            if "enabled" in patch["lint"]:
                c.lint.enabled = patch["lint"]["enabled"]
            if "strict_mode" in patch["lint"]:
                c.lint.strict_mode = patch["lint"]["strict_mode"]
        if "ui" in patch:
            if "default_theme" in patch["ui"]:
                c.ui.default_theme = patch["ui"]["default_theme"]
            if "default_view" in patch["ui"]:
                c.ui.default_view = patch["ui"]["default_view"]
        if "advanced" in patch:
            if "show_skills" in patch["advanced"]:
                c.advanced.show_skills = patch["advanced"]["show_skills"]
            if "show_meta" in patch["advanced"]:
                c.advanced.show_meta = patch["advanced"]["show_meta"]
            if "show_memory" in patch["advanced"]:
                c.advanced.show_memory = patch["advanced"]["show_memory"]
            if "show_other" in patch["advanced"]:
                c.advanced.show_other = patch["advanced"]["show_other"]

        self._persist_config(patch)
        logger.info("配置已更新：{}", patch)
        return self.get_config_dict()

    def _persist_config(self, patch: dict) -> None:
        """把 patch 合并进现有 config.toml（手工渲染固定 schema，避免引入 tomli-w）。"""
        raw: dict = {}
        if self.config.config_file.exists():
            try:
                import tomllib

                with open(self.config.config_file, "rb") as f:
                    raw = tomllib.load(f)
            except (OSError, ValueError):
                raw = {}
        for section, values in patch.items():
            raw.setdefault(section, {}).update(values)

        lines: list[str] = []
        for section in ("server", "backup", "lint", "ui", "advanced", "openclaw"):
            values = raw.get(section)
            if not values:
                continue
            lines.append(f"[{section}]")
            for k, v in values.items():
                if isinstance(v, bool):
                    lines.append(f"{k} = {str(v).lower()}")
                elif isinstance(v, int):
                    lines.append(f"{k} = {v}")
                else:
                    lines.append(f'{k} = "{v}"')
            lines.append("")
        self.config.config_file.write_text("\n".join(lines), encoding="utf-8")
