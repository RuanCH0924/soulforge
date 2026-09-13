"""SuperSyncService：超级同步的后端管理面。

职责：
- 配置：读取 / 更新 <data_dir>/super_sync/config.json（同步范围）
- 运行：以「分离进程」方式启动 / 停止独立脚本 backend/super_sync.py
        （父进程退出后脚本继续跑；命令行手动启动也能被本服务识别）
- 状态：读取 status.json + 进程存活 / 心跳时效，判定 运行中 / 已停止 / 异常
- 日志：解析 logs/*.jsonl，支持按级别、时间范围筛选与导出

状态判定（UI 侧 3 秒内可感知）：
- 无状态文件 / 进程不在  → stopped
- 进程在 + 心跳新鲜      → running
- 进程在 + 心跳超时      → error（脚本可能卡死）
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config import Config
from app.services import super_sync_common as ssc
from app.services.agent_discovery import AgentDiscovery

MAX_LOG_FILES = 40  # 单次查询最多解析的日志文件数（≈ 留存 30+ 天）


class SuperSyncService:
    def __init__(self, config: Config, discovery: AgentDiscovery):
        self.config = config
        self.discovery = discovery

    # ---------------------------------------------------------------- 路径

    @property
    def data_dir(self) -> Path:
        return self.config.data_dir

    @property
    def script_path(self) -> Path:
        # backend/app/services/super_sync_service.py -> backend/super_sync.py
        return Path(__file__).resolve().parents[2] / "super_sync.py"

    # ---------------------------------------------------------------- 配置

    def get_config(self) -> dict:
        return ssc.load_config(self.data_dir)

    def update_config(self, patch: dict) -> dict:
        """局部合并更新同步范围（字段已由 Pydantic 校验），返回落盘后的配置。"""
        merged = {**self.get_config(), **(patch or {})}
        return ssc.save_config(self.data_dir, merged)

    # ---------------------------------------------------------------- 状态

    def get_status(self) -> dict:
        raw = ssc.read_status(self.data_dir) or {}
        pid = raw.get("pid")
        alive = ssc.pid_alive(pid)
        heartbeat_ts = ssc.parse_ts(raw.get("last_heartbeat"))
        age = (time.time() - heartbeat_ts) if heartbeat_ts else None
        reported = raw.get("state")

        if reported == "running" and alive:
            state = "running" if (age is None or age <= ssc.HEARTBEAT_TIMEOUT_SECONDS) else "error"
        elif reported == "error" and alive:
            state = "error"
        else:
            state = "stopped"

        return {
            "state": state,
            "pid": pid,
            "pid_alive": alive,
            "source": raw.get("source"),
            "started_at": raw.get("started_at"),
            "last_heartbeat": raw.get("last_heartbeat"),
            "heartbeat_age_seconds": round(age, 2) if age is not None else None,
            "interval_seconds": raw.get("interval_seconds", self.get_config()["interval_seconds"]),
            "agents": raw.get("agents") or self.get_config()["agents"],
            "synced_total": raw.get("synced_total", 0),
            "ticks": raw.get("ticks", 0),
            "last_sync_at": raw.get("last_sync_at"),
            "last_duration_ms": raw.get("last_duration_ms"),
            "last_error": raw.get("last_error"),
        }

    # ---------------------------------------------------------------- 启动 / 停止

    def start(self, source: str = "ui") -> dict:
        """以分离进程启动脚本；若已在运行则直接返回当前状态。"""
        current = self.get_status()
        if current["state"] == "running":
            return current

        workspace = self.config.openclaw_dir
        cmd = [
            sys.executable, str(self.script_path),
            "--data-dir", str(self.data_dir),
            "--openclaw-dir", str(workspace),
            "--source", source,
        ]
        stdio_log = ssc.log_dir(self.data_dir) / ssc.STDIO_LOG_FILENAME
        stdio_log.parent.mkdir(parents=True, exist_ok=True)
        handle = open(stdio_log, "ab")  # noqa: SIM115 - 子进程继承句柄后由父进程关闭

        kwargs: dict = {
            "cwd": str(self.script_path.parent),  # 保证脚本内 `import app` 可用
            "stdin": subprocess.DEVNULL,
            "stdout": handle,
            "stderr": handle,
            "close_fds": True,
        }
        if os.name == "nt":
            # DETACHED_PROCESS：完全脱离父进程；父进程退出后脚本继续运行
            kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(cmd, **kwargs)
        finally:
            handle.close()

        # 等待脚本写入首个心跳（最多 ~3 秒）
        for _ in range(30):
            time.sleep(0.1)
            status = self.get_status()
            if status["state"] == "running":
                return status
        return self.get_status()

    def stop(self) -> dict:
        """终止独立脚本（Windows: taskkill /F；POSIX: SIGTERM），等待状态收敛。"""
        status = self.get_status()
        pid = status.get("pid")
        if status["state"] == "stopped" or not pid:
            return status
        self._terminate(int(pid))
        for _ in range(30):
            time.sleep(0.1)
            latest = self.get_status()
            if latest["state"] == "stopped":
                return latest
        return self.get_status()

    @staticmethod
    def _terminate(pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    # ---------------------------------------------------------------- 日志

    def _log_files(self) -> list[Path]:
        files = sorted(
            ssc.log_dir(self.data_dir).glob(f"{ssc.LOG_PREFIX}*{ssc.LOG_SUFFIX}"),
            key=lambda p: p.name,
            reverse=True,
        )
        return files[:MAX_LOG_FILES]

    def _read_records(
        self,
        levels: list[str] | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> list[dict]:
        wanted = {lv.upper() for lv in (levels or []) if lv}
        records: list[dict] = []
        for path in self._log_files():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if wanted and str(record.get("level", "")).upper() not in wanted:
                    continue
                ts = ssc.parse_ts(record.get("ts_unix") or record.get("ts"))
                if since is not None and (ts is None or ts < since):
                    continue
                if until is not None and (ts is None or ts > until):
                    continue
                records.append(record)
        return records

    def query_logs(
        self,
        *,
        levels: list[str] | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        records = self._read_records(levels=levels, since=since, until=until)
        records.sort(key=lambda r: ssc.parse_ts(r.get("ts_unix") or r.get("ts")) or 0, reverse=True)
        total = len(records)
        return {
            "items": records[offset:offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "retention_days": self.get_config()["retention_days"],
        }

    def export_logs(
        self,
        *,
        levels: list[str] | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> tuple[str, bytes]:
        """导出筛选后的日志为 .jsonl，返回 (文件名, 内容字节)。"""
        records = self._read_records(levels=levels, since=since, until=until)
        records.sort(key=lambda r: ssc.parse_ts(r.get("ts_unix") or r.get("ts")) or 0)
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return f"super-sync-logs-{stamp}.jsonl", payload
