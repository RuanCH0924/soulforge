"""超级同步（Super Sync）共享定义：路径、配置、状态、日志格式、进程存活检测。

三处复用，保证「独立脚本」与「后端服务 / UI」看到完全一致的落盘协议：
- 独立守护脚本 backend/super_sync.py（跨进程、可脱离主进程运行）
- 后端 SuperSyncService（启动 / 停止 / 查状态 / 查日志）
- 前端（经 API 序列化展示）

数据落盘（全部位于 <data_dir>/super_sync/）：
- config.json   同步范围配置（参与 Agent + 每个 Agent 的文件清单）
- status.json   运行状态 + 心跳（脚本每轮写入）
- logs/*.jsonl  结构化日志（按天滚动，留存 ≥ 30 天）
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SUPER_SYNC_DIRNAME = "super_sync"
CONFIG_FILENAME = "config.json"
STATUS_FILENAME = "status.json"
LOG_DIRNAME = "logs"
LOG_PREFIX = "super_sync-"
LOG_SUFFIX = ".jsonl"
STDIO_LOG_FILENAME = "super_sync-stdio.log"

#: 允许纳入超级同步的文档白名单（仅这 5 个核心文档，其余一律忽略）
SYNC_FILENAMES = ("SOUL.md", "AGENTS.md", "USER.md", "MEMORY.md", "IDENTITY.md")

DEFAULT_INTERVAL_SECONDS = 1.0
MIN_INTERVAL_SECONDS = 0.5
MAX_INTERVAL_SECONDS = 60.0
DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 30  # 需求：日志留存不得少于 30 天
HEARTBEAT_TIMEOUT_SECONDS = 5.0  # 心跳超过该秒数视为「异常」（脚本可能卡死）

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


# ---------------------------------------------------------------- 路径


def super_sync_dir(data_dir: Path | str) -> Path:
    return Path(data_dir) / SUPER_SYNC_DIRNAME


def config_path(data_dir: Path | str) -> Path:
    return super_sync_dir(data_dir) / CONFIG_FILENAME


def status_path(data_dir: Path | str) -> Path:
    return super_sync_dir(data_dir) / STATUS_FILENAME


def log_dir(data_dir: Path | str) -> Path:
    return super_sync_dir(data_dir) / LOG_DIRNAME


# ---------------------------------------------------------------- 时间


def now_iso() -> str:
    """本地时间 ISO 字符串（毫秒精度），用于状态 / 日志时间戳展示。"""
    return datetime.now().isoformat(timespec="milliseconds")


def parse_ts(value: Any) -> float | None:
    """把日志 / 状态里的时间（ISO 字符串或 unix 秒）解析成 unix 秒。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return None


# ---------------------------------------------------------------- 原子写


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_file(path: Path, data: bytes) -> None:
    """同步引擎写目标文件用：先写临时文件再替换，避免读到半截内容。"""
    _atomic_write_bytes(path, data)


# ---------------------------------------------------------------- 配置


def default_config() -> dict:
    """默认同步范围：不选任何 Agent / 文件（功能需显式配置后才有同步对象）。"""
    return {
        "interval_seconds": DEFAULT_INTERVAL_SECONDS,
        "retention_days": DEFAULT_RETENTION_DAYS,
        "agents": [],
        "files": {},
    }


def _clamp_interval(value: Any) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS
    return float(min(MAX_INTERVAL_SECONDS, max(MIN_INTERVAL_SECONDS, num)))


def normalize_config(raw: Any) -> dict:
    """收敛配置：类型校正 + 边界钳制 + 去重 + 相对路径规范化。"""
    raw = raw if isinstance(raw, dict) else {}
    retention = raw.get("retention_days", DEFAULT_RETENTION_DAYS)
    try:
        retention_days = int(retention)
    except (TypeError, ValueError):
        retention_days = DEFAULT_RETENTION_DAYS
    retention_days = max(MIN_RETENTION_DAYS, retention_days)

    agents: list[str] = []
    for item in raw.get("agents") or []:
        agent_id = str(item).strip()
        if agent_id and agent_id not in agents:
            agents.append(agent_id)

    files_raw = raw.get("files") or {}
    files: dict[str, list[str]] = {}
    for agent_id in agents:
        items = files_raw.get(agent_id) if isinstance(files_raw, dict) else None
        cleaned = {
            str(p).replace("\\", "/").lstrip("/")
            for p in (items or [])
            if str(p).strip()
        }
        # 仅保留白名单内的核心文档，其余（含历史遗留配置）一律丢弃
        files[agent_id] = sorted(p for p in cleaned if p in SYNC_FILENAMES)

    return {
        "interval_seconds": _clamp_interval(raw.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)),
        "retention_days": retention_days,
        "agents": agents,
        "files": files,
    }


def load_config(data_dir: Path | str) -> dict:
    """读取同步配置；文件不存在 / 损坏时回落默认配置。"""
    path = config_path(data_dir)
    if not path.exists():
        return default_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default_config()
    return normalize_config(raw)


def save_config(data_dir: Path | str, config: dict) -> dict:
    """持久化同步配置（已收敛），返回落盘后的配置。"""
    normalized = normalize_config(config)
    _atomic_write_text(config_path(data_dir), json.dumps(normalized, ensure_ascii=False, indent=2))
    return normalized


# ---------------------------------------------------------------- 状态


def read_status(data_dir: Path | str) -> dict | None:
    path = status_path(data_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def write_status(data_dir: Path | str, status: dict) -> None:
    _atomic_write_text(status_path(data_dir), json.dumps(status, ensure_ascii=False, indent=2))


def pid_alive(pid: Any) -> bool:
    """跨平台判断进程是否存在。

    注意：Windows 上不能用 os.kill(pid, 0)（会真的终止进程），改用 tasklist 查询。
    """
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False

    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid_int}", "/NH", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return str(pid_int) in (proc.stdout or "")

    try:
        os.kill(pid_int, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 存在但无权限发信号
    except OSError:
        return False
    return True


# ---------------------------------------------------------------- 日志


def log_file_path(data_dir: Path | str, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d")
    return log_dir(data_dir) / f"{LOG_PREFIX}{stamp}{LOG_SUFFIX}"


class SuperSyncLogger:
    """结构化日志（JSON Lines，按天滚动，超期自动清理）。

    一条记录样例：
    {"ts": "2026-09-13T12:00:00.123", "ts_unix": 1757..., "level": "INFO",
     "event": "sync", "path": "SOUL.md", "source_agent": "alpha",
     "target_agent": "beta", "result": "ok", "size_bytes": 12,
     "sha256": "...", "diff": "...", "error": null, "message": ""}
    """

    def __init__(self, data_dir: Path | str, retention_days: int = DEFAULT_RETENTION_DAYS,
                 console: bool = True):
        self.data_dir = Path(data_dir)
        self.retention_days = max(MIN_RETENTION_DAYS, int(retention_days))
        self.console = console
        self._writes = 0
        log_dir(self.data_dir).mkdir(parents=True, exist_ok=True)
        self.prune()

    def prune(self) -> int:
        """删除超过留存期限的日志文件，返回删除数量。"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        removed = 0
        for path in log_dir(self.data_dir).glob(f"{LOG_PREFIX}*{LOG_SUFFIX}"):
            stamp = path.stem[len(LOG_PREFIX):]
            try:
                file_day = datetime.strptime(stamp, "%Y%m%d")
            except ValueError:
                continue
            if file_day < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    def log(self, level: str, event: str, message: str = "", **fields: Any) -> dict:
        level = str(level).upper()
        if level not in LOG_LEVELS:
            level = "INFO"
        moment = datetime.now()
        record: dict[str, Any] = {
            "ts": moment.isoformat(timespec="milliseconds"),
            "ts_unix": moment.timestamp(),
            "level": level,
            "event": event,
            "message": message,
        }
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False)
        try:
            with open(log_file_path(self.data_dir, moment), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        if self.console:
            print(f"[{record['ts']}] {level:<7} {event} {message}".rstrip(), flush=True)
        self._writes += 1
        if self._writes % 200 == 0:
            self.prune()
        return record
