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
    reason: Mapped[str | None] = mapped_column(String, nullable=True)  # auto-write | manual | pre-rollback | pre-sync
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
    # 预设参考文档（Markdown；新形态不含 YAML，旧值兼容、读取时惰性归一）
    template_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 结构化格式化规则（见 docs/PRESET-TEMPLATE-REFACTOR-PLAN.md）：
    # {schema, section_heading_level, require_frontmatter}
    # 为空 = 存量数据，读取时由 template_md 的旧 YAML / 全局默认补齐（惰性兼容，不写库）
    format_rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sections_json: Mapped[str] = mapped_column(Text, nullable=False)  # [{title, required, order, hint}]（由预设参考文档派生）
    frontmatter_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_rules: Mapped[str | None] = mapped_column(Text, nullable=True)  # 修改要求（逐条自由文本）
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 1=系统预设不可删
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # PUT 后自增
    # 非空 = 该预设已退役（内置预设随版本下线）：不再出现在列表里，但行保留，
    # 以免历史上引用它的批次 / AI 任务读取时报 404。见 preset_service.BUILTIN_PRESETS_RETIRED
    retired_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)


class PresetVersionRow(Base):
    """预设版本历史（每次 create/update 保存一份快照，支持回溯）。

    schema 见 docs/DATA-MODEL.md 2.5 / 2.6「version 自增，保留历史」。
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
    """LLM Provider 配置（Phase 2.5 · M12）。schema 见 docs/DATA-MODEL.md 2.7。

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
    """AI 整理任务（Phase 2.5 · M13）。schema 见 docs/DATA-MODEL.md 2.8。

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


class DailyRunRow(Base):
    """工作日志标准化批次（M15 · P2）。schema 见 docs/DATA-MODEL.md 2.9。

    状态机：`planned`（已创建，正在逐日生成）→ `awaiting_confirm`（计划已出，等确认）
    → `applied` / `partially_applied` / `needs_review`；另有 `rejected`（用户拒绝，未写入）、
    `failed`（生成阶段整体失败：LLM 报错 / 超 token 预算）、`empty`（该范围没有可整理的日子）。

    批次**不复用 `ai_jobs`**：后者是单文件语义，混用会污染既有状态机。
    """

    __tablename__ = "daily_runs"
    __table_args__ = (
        Index("idx_daily_runs_agent", "agent_id"),
        Index("idx_daily_runs_status", "status"),
        Index("idx_daily_runs_key", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # run-<uuid hex>
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    date_from: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD
    date_to: Mapped[str] = mapped_column(String, nullable=False)
    preset_id: Mapped[str] = mapped_column(String, nullable=False)
    preset_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 批次绑定的预设版本（可回溯）
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)  # 同键重复提交 → 复用既有批次
    extra_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    days_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = 不限
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DailyRunItemRow(Base):
    """批次的逐日条目（M15 · P2）。schema 见 docs/DATA-MODEL.md 2.9。

    一天一条：来源清单 + 归并内容 + diff + 拟删碎片 + 强规则报告 + 该日 token 成本。
    `item_status`：`planned`（已生成计划）/ `failed`（生成失败）/ `blocked`（写前验收不过，未写入）
    / `applied`（已写入且碎片已清理）/ `partially_applied`（日文件已写，碎片删失败）/ `skipped`（人工跳过）。
    """

    __tablename__ = "daily_run_items"
    __table_args__ = (
        Index("idx_daily_run_items_run", "run_id"),
        UniqueConstraint("run_id", "date", name="uq_daily_run_items_run_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    target_path: Mapped[str] = mapped_column(String, nullable=False)  # memory/YYYY-MM-DD.md
    source_hashes_json: Mapped[str] = mapped_column(Text, nullable=False)  # {path: sha256}，乐观锁用
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 各来源的体积/剥壳事实
    fragments_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 拟删碎片路径清单
    # 大模型判定为「无意义」的碎片（仅 auto_delete_meaningless_logs 开启时非空）：
    # [{path, dimension, reason, backup_path?, sha256?, archived_at?}]，删除前已备份归档
    meaningless_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    unified_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    format_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    lint_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 非空 = 模型判定「本日无可归档内容」（值为一句话理由）：该日不产出日文件，
    # 只清理 B/C 碎片；A 类主文件 memory/YYYY-MM-DD.md 保持不动
    empty_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending | applied | skipped
    item_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    applied_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_now, onupdate=_now)


class SummaryRunRow(Base):
    """工作日志总结（记忆归纳，M16）批次。一次归纳只产出**一份**汇总文件。

    状态机：`planned`（已创建，正在归纳）→ `awaiting_confirm`（计划已出，等确认）
    → `applied` / `needs_review`；另有 `rejected`（用户拒绝，未写入）、
    `failed`（生成失败：LLM 报错 / 强规则不过 / 来源超限）、`empty`（范围内没有可归纳的来源）。

    与 M15 的区别：M15 是「同一天多来源 → 1 个日文件」的逐日归并（两表）；
    M16 是「一段时间的全部来源 → 1 份综述」的单份产物，因此只有批次表。
    源文件**默认不动**（只读归纳）；`cleanup_*` 记录确认后可选的「清理源文件」动作。
    """

    __tablename__ = "summary_runs"
    __table_args__ = (
        Index("idx_summary_runs_agent", "agent_id"),
        Index("idx_summary_runs_status", "status"),
        Index("idx_summary_runs_key", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # run-<uuid hex>
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    date_from: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD
    date_to: Mapped[str] = mapped_column(String, nullable=False)
    preset_id: Mapped[str] = mapped_column(String, nullable=False)
    preset_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)  # 同键重复提交 → 复用
    extra_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str] = mapped_column(String, nullable=False)  # memory/<span>-记忆归纳.md
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_hashes_json: Mapped[str] = mapped_column(Text, nullable=False)  # {path: sha256}，乐观锁
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 各来源的体积/剥壳事实
    output_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    unified_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    format_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    lint_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = 不限
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 可选动作：汇总确认写入后，把范围内的源文件移入回收站（默认不清理）
    cleanup_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cleanup_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # {deleted: [...], failed: [...]}
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
            "presets": [("template_md", "TEXT"), ("retired_at", "INTEGER"),
                        ("format_rules_json", "TEXT")],
            "daily_run_items": [("empty_reason", "TEXT"), ("meaningless_json", "TEXT")],
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
