"""SQLite 数据层：4 张表（agents / files / backups / audit_log）。

Schema 定义见 docs/DATA-MODEL.md。SQLAlchemy 2.x Mapped[] 风格。
数据库不备份 —— 重扫即可重建（doc 明确）。
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import (
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
