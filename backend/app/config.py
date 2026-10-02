"""全局配置：路径、config.toml、环境变量覆盖。

优先级：环境变量 > config.toml > 内置默认值。
所有路径都可用环境变量覆盖（测试场景必须）：
- SOULFORGE_DATA_DIR      数据目录（默认 <项目根>/.soulforge，全部项目数据内聚于项目目录）
- SOULFORGE_OPENCLAW_DIR  OpenClaw 根目录（默认自动探测：项目上一级 workspace 所属的 OpenClaw 根）
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

# 项目根目录：backend/app/config.py -> soulforge/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# 数据目录固定放在项目目录内，避免依赖任何外部全局路径（如 %USERPROFILE%）
DEFAULT_DATA_DIR = PROJECT_ROOT / ".soulforge"
# OpenClaw 根目录：项目位于 <OpenClaw根>/workspace/projects/soulforge，向上三级即 OpenClaw 根
_OPENCLAW_CANDIDATE = PROJECT_ROOT.parent.parent.parent
DEFAULT_OPENCLAW_DIR = _OPENCLAW_CANDIDATE if (_OPENCLAW_CANDIDATE / "openclaw.json").exists() else Path.home() / ".openclaw"
DEFAULT_PORT = 8848


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT


@dataclass
class BackupConfig:
    retention_days: int = 30
    auto_backup_on_write: bool = True


@dataclass
class LintConfig:
    enabled: bool = True
    strict_mode: bool = False  # true 时违规阻止保存


@dataclass
class UIConfig:
    default_theme: str = "auto"  # auto | light | dark
    default_view: str = "tree"  # tree | list


@dataclass
class AdvancedConfig:
    show_skills: bool = False
    show_meta: bool = False
    show_memory: bool = False
    show_other: bool = False


@dataclass
class OpenClawConfig:
    dir: str = ""  # 空 = 使用默认 ~/.openclaw


@dataclass
class DailyStandardizerConfig:
    """工作日志标准化（M15）护栏。触发方式是手动批次，**不含任何定时字段**。

    - `max_days_per_run`：单批天数上限（防失控）
    - `token_budget`：单批 token 预算，0 = 不限；越限即中止该批次且不写入任何文件
    - `provider_id`：默认 LLM provider（UI 可覆盖）
    - `dry_run_only`：全局「关闭执行（只出计划）」开关，异常时一键降级为 dry-run
    - `auto_delete_meaningless_logs`：是否启用「大模型无意义日志自动删除」。
      默认 `False`（关闭，保持既有行为：碎片仅走回收站、不做大模型筛选）。
      开启后，批次生成计划时会额外调一次大模型对当日碎片做无意义判定，
      被判定为无意义的日志在删除前会先写入 7 天可追溯备份归档（见
      `app.services.meaningless_log_archive`），再走回收站删除。
    """

    max_days_per_run: int = 31
    token_budget: int = 200_000
    provider_id: str = ""
    dry_run_only: bool = False
    auto_delete_meaningless_logs: bool = False


@dataclass
class SummarizerConfig:
    """工作日志总结（记忆归纳，M16）护栏。触发方式同样是手动批次，**不含任何定时字段**。

    - `max_days_per_run`：单次归纳的日期跨度上限（天）
    - `token_budget`：单次 token 预算，0 = 不限
    - `provider_id`：默认 LLM provider（UI 可覆盖）
    - `dry_run_only`：全局「关闭执行（只出计划）」开关
    """

    max_days_per_run: int = 62
    token_budget: int = 300_000
    provider_id: str = ""
    dry_run_only: bool = False


@dataclass
class Config:
    data_dir: Path
    openclaw_dir: Path
    server: ServerConfig = field(default_factory=ServerConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    lint: LintConfig = field(default_factory=LintConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    daily_standardizer: DailyStandardizerConfig = field(default_factory=DailyStandardizerConfig)
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)

    # ---- 派生路径 ----
    @property
    def db_path(self) -> Path:
        return self.data_dir / "index.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.toml"

    @property
    def openclaw_config_file(self) -> Path:
        return self.openclaw_dir / "openclaw.json"


def _env_dir(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def load_config() -> Config:
    data_dir = _env_dir("SOULFORGE_DATA_DIR", DEFAULT_DATA_DIR)
    openclaw_dir = _env_dir("SOULFORGE_OPENCLAW_DIR", DEFAULT_OPENCLAW_DIR)

    raw: dict = {}
    if data_dir.joinpath("config.toml").exists():
        with open(data_dir / "config.toml", "rb") as f:
            raw = tomllib.load(f)

    def section(name: str) -> dict:
        return raw.get(name, {}) or {}

    server_raw = section("server")
    backup_raw = section("backup")
    lint_raw = section("lint")
    ui_raw = section("ui")
    advanced_raw = section("advanced")
    openclaw_raw = section("openclaw")
    daily_raw = section("daily_standardizer")
    summary_raw = section("summarizer")

    openclaw_dir = Path(openclaw_raw.get("dir", "")).expanduser() if openclaw_raw.get("dir") else openclaw_dir

    return Config(
        data_dir=data_dir,
        openclaw_dir=openclaw_dir,
        server=ServerConfig(
            host=server_raw.get("host", "127.0.0.1"),
            port=int(server_raw.get("port", DEFAULT_PORT)),
        ),
        backup=BackupConfig(
            retention_days=int(backup_raw.get("retention_days", 30)),
            auto_backup_on_write=bool(backup_raw.get("auto_backup_on_write", True)),
        ),
        lint=LintConfig(
            enabled=bool(lint_raw.get("enabled", True)),
            strict_mode=bool(lint_raw.get("strict_mode", False)),
        ),
        ui=UIConfig(
            default_theme=ui_raw.get("default_theme", "auto"),
            default_view=ui_raw.get("default_view", "tree"),
        ),
        advanced=AdvancedConfig(
            show_skills=bool(advanced_raw.get("show_skills", False)),
            show_meta=bool(advanced_raw.get("show_meta", False)),
            show_memory=bool(advanced_raw.get("show_memory", False)),
            show_other=bool(advanced_raw.get("show_other", False)),
        ),
        openclaw=OpenClawConfig(dir=str(openclaw_dir)),
        daily_standardizer=DailyStandardizerConfig(
            max_days_per_run=int(daily_raw.get("max_days_per_run", 31)),
            token_budget=int(daily_raw.get("token_budget", 200_000)),
            provider_id=str(daily_raw.get("provider_id", "")),
            dry_run_only=bool(daily_raw.get("dry_run_only", False)),
            auto_delete_meaningless_logs=bool(
                daily_raw.get("auto_delete_meaningless_logs", False)),
        ),
        summarizer=SummarizerConfig(
            max_days_per_run=int(summary_raw.get("max_days_per_run", 62)),
            token_budget=int(summary_raw.get("token_budget", 300_000)),
            provider_id=str(summary_raw.get("provider_id", "")),
            dry_run_only=bool(summary_raw.get("dry_run_only", False)),
        ),
    )
