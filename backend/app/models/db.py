"""SQLite 数据层：4 张表（agents / files / backups / audit_log）。

Schema 定义见 docs/DATA-MODEL.md。SQLAlchemy 2.x Mapped[] 风格。
数据库不备份 —— 重扫即可重建（doc 明确）。
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import (
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def _now() -> int:
    return int(time.time())


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    last_scanned_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)


class FileRow(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("agent_id", "path", name="uq_files_agent_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, index=True)  # CORE | MEMORY | SKILL | META | OTHER
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mtime: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    last_lint_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lint_warnings: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)


class BackupRow(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    backup_path: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)  # auto-write | manual | pre-rollback | pre-import
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, index=True)


class AuditRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)  # write | delete | rollback | ...
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    target_path: Mapped[str | None] = mapped_column(String, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[str] = mapped_column(String, nullable=False, default="local")
    result: Mapped[str] = mapped_column(String, nullable=False, default="ok")  # ok | failed


class PresetRow(Base):
    """文档预设（Phase 2.5 · M11）。schema 见 docs/DATA-MODEL.md 2.5。"""

    __tablename__ = "presets"
    __table_args__ = (
        Index("idx_presets_target", "target_file_type"),
        Index("idx_presets_system", "is_system"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID（内置预设为 preset-*）
    name: Mapped[str] = mapped_column(String, nullable=False)
    target_file_type: Mapped[str] = mapped_column(String, nullable=False)  # SOUL/AGENTS/MEMORY/USER/.../ANY
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    template_md: Mapped[str | None] = mapped_column(Text, nullable=True)  # 标准 Markdown 模板文档（YAML 规则+骨架）
    sections_json: Mapped[str] = mapped_column(Text, nullable=False)  # [{title, required, order, hint}]（由模板派生）
    frontmatter_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 1=系统预设不可删
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # PUT 后自增
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)


class PresetVersionRow(Base):
    """预设版本历史（每次 create/update 保存一份快照，支持回溯）。

    schema 见 docs/DATA-MODEL.md 2.5「version 自增，保留历史」。
    """

    __tablename__ = "preset_versions"
    __table_args__ = (Index("idx_preset_versions_preset", "preset_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    preset_id: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)  # 与 presets.version 对应的快照版本
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)  # 完整预设内容快照
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, index=True)
    user: Mapped[str] = mapped_column(String, nullable=False, default="local")


class LLMProviderRow(Base):
    """LLM Provider 配置（Phase 2.5 · M12）。schema 见 docs/DATA-MODEL.md 2.6。

    API key 以 Fernet 密文存储（api_key_encrypted），任何响应都不回显明文。
    """

    __tablename__ = "llm_providers"
    __table_args__ = (Index("idx_llm_providers_enabled", "enabled"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)  # provider 名（业务唯一）
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet 密文
    model: Mapped[str] = mapped_column(String, nullable=False)
    protocol: Mapped[str] = mapped_column(String, nullable=False)  # openai-completions | anthropic-messages
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)


class AIJobRow(Base):
    """AI 整理任务（Phase 2.5 · M13）。schema 见 docs/DATA-MODEL.md 2.7。

    状态机：pending→running→awaiting_confirm→(applied|rejected|superseded)；失败→failed。
    """

    __tablename__ = "ai_jobs"
    __table_args__ = (
        Index("idx_ai_jobs_status", "status"),
        Index("idx_ai_jobs_agent_file", "agent_id", "file_path"),
        Index("idx_ai_jobs_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    preset_id: Mapped[str] = mapped_column(String, nullable=False)
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # pending|running|awaiting_confirm|applied|rejected|failed|superseded
    input_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Database:
    """单进程单连接 SQLite，WAL 模式。"""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _set_pragma(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        """轻量迁移：为已存在的旧表补齐新增列（create_all 不会改动已存在的表）。"""
        columns = {
            "presets": [("template_md", "TEXT")],
        }
        with self.engine.connect() as conn:
            for table, adds in columns.items():
                existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                for col, col_type in adds:
                    if col not in existing:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            conn.commit()

    def session(self):
        return self.Session()

    def vacuum(self) -> None:
        with self.engine.connect() as conn:
            conn.exec_driver_sql("VACUUM")

    def count(self, table: str) -> int:
        with self.session() as s:
            return s.query(Base.metadata.tables[table]).count()  # type: ignore[arg-type]


def init_db(db_path: Path) -> Database:
    db = Database(db_path)
    db.init_db()
    return db
