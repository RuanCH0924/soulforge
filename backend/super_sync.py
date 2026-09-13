#!/usr/bin/env python
"""超级同步独立守护脚本（可脱离 Soulforge 主进程运行）。

两种启动方式，功能完全一致：
1. UI 按钮：后端以「分离进程」方式拉起本脚本（父进程退出后本脚本继续运行）；
2. 命令行：cd backend && python super_sync.py [--data-dir ...] [--openclaw-dir ...]

用法：
    python super_sync.py                     # 按 <data_dir>/super_sync/config.json 持续运行
    python super_sync.py --once              # 只跑一轮（自检 / 测试）
    python super_sync.py --source cli        # 标记启动来源（写入状态，便于 UI 展示）
    python super_sync.py --interval 1        # 覆盖轮询间隔（秒）

运行期间每个轮询周期都会写入 <data_dir>/super_sync/status.json（含心跳），
并追加结构化日志到 <data_dir>/super_sync/logs/super_sync-YYYYMMDD.jsonl。
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

# 保证可直接以脚本方式运行：把 backend/ 加入模块搜索路径
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config, load_config  # noqa: E402
from app.services import super_sync_common as ssc  # noqa: E402
from app.services.agent_discovery import AgentDiscovery  # noqa: E402
from app.services.super_sync_engine import EngineStats, SuperSyncEngine  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soulforge 超级同步守护脚本")
    parser.add_argument("--data-dir", default=None, help="Soulforge 数据目录（默认取配置）")
    parser.add_argument("--openclaw-dir", default=None, help="OpenClaw 根目录（默认取配置）")
    parser.add_argument("--source", default="cli", choices=["ui", "cli"], help="启动来源，仅用于状态展示")
    parser.add_argument("--interval", type=float, default=None, help="轮询间隔秒数（覆盖配置）")
    parser.add_argument("--once", action="store_true", help="只执行一轮同步后退出")
    return parser.parse_args(argv)


def _build_workspaces(config: Config, sync_config: dict) -> dict[str, Path]:
    """把配置中选中的 Agent 解析成 {agent_id: workspace 路径}（仅保留目录存在的）。"""
    discovered = {a.id: Path(a.workspace) for a in AgentDiscovery(config).discover()}
    workspaces: dict[str, Path] = {}
    for agent_id in sync_config["agents"]:
        workspace = discovered.get(agent_id)
        if workspace is not None and workspace.is_dir():
            workspaces[agent_id] = workspace
    return workspaces


def _make_heartbeat(data_dir: Path, sync_config: dict, workspaces: dict[str, Path],
                    started_at: str, source: str):
    def heartbeat(stats: EngineStats) -> None:
        ssc.write_status(data_dir, {
            "state": "running",
            "pid": os.getpid(),
            "source": source,
            "started_at": started_at,
            "last_heartbeat": ssc.now_iso(),
            "interval_seconds": sync_config["interval_seconds"],
            "agents": list(workspaces),
            "synced_total": stats.synced,
            "ticks": stats.ticks,
            "last_sync_at": stats.last_sync_at,
            "last_duration_ms": stats.last_duration_ms,
            "last_error": stats.last_error,
        })
    return heartbeat


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base = load_config()
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else base.data_dir
    openclaw_dir = Path(args.openclaw_dir).expanduser() if args.openclaw_dir else base.openclaw_dir
    config = Config(data_dir=data_dir, openclaw_dir=openclaw_dir)

    sync_config = ssc.load_config(data_dir)
    if args.interval is not None:
        sync_config = ssc.normalize_config({**sync_config, "interval_seconds": args.interval})

    # 互斥：已有脚本在跑则拒绝重复启动
    existing = ssc.read_status(data_dir)
    if existing and existing.get("state") == "running" and ssc.pid_alive(existing.get("pid")):
        print(f"[super-sync] 已在运行（pid={existing.get('pid')}），本次启动取消。", flush=True)
        return 1

    workspaces = _build_workspaces(config, sync_config)
    logger = ssc.SuperSyncLogger(data_dir, sync_config["retention_days"])
    started_at = ssc.now_iso()
    logger.log(
        "INFO", "start",
        f"超级同步启动（source={args.source}，interval={sync_config['interval_seconds']}s，"
        f"agents={list(workspaces) or '无'}）",
        source=args.source, agents=list(workspaces),
        interval_seconds=sync_config["interval_seconds"],
    )
    if not workspaces:
        logger.log("WARNING", "start", "没有可用的 Agent：请先在 UI「同步范围」中选择 Agent 与文件。")

    engine = SuperSyncEngine(workspaces, sync_config, logger)
    heartbeat = _make_heartbeat(data_dir, sync_config, workspaces, started_at, args.source)
    stop_event = threading.Event()

    def _handle_signal(signum, _frame):  # noqa: ANN001
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass

    heartbeat(engine.stats)  # 立即写一次状态，让 UI 尽快感知「运行中」
    exit_code = 0
    try:
        if args.once:
            actions = engine.sync_once()
            heartbeat(engine.stats)
            logger.log("INFO", "once", f"单次同步完成：{len(actions)} 个同步动作")
        else:
            engine.run(stop_event, heartbeat)
    except Exception as exc:  # noqa: BLE001 - 守护进程兜底
        exit_code = 1
        engine.stats.last_error = str(exc)
        logger.log("ERROR", "error", f"运行异常退出：{exc}")
        ssc.write_status(data_dir, {
            "state": "error", "pid": os.getpid(), "source": args.source,
            "started_at": started_at, "last_heartbeat": ssc.now_iso(),
            "interval_seconds": sync_config["interval_seconds"], "agents": list(workspaces),
            "synced_total": engine.stats.synced, "ticks": engine.stats.ticks,
            "last_sync_at": engine.stats.last_sync_at, "last_error": str(exc),
        })
    finally:
        if exit_code == 0:
            ssc.write_status(data_dir, {
                "state": "stopped", "pid": os.getpid(), "source": args.source,
                "started_at": started_at, "last_heartbeat": ssc.now_iso(),
                "interval_seconds": sync_config["interval_seconds"], "agents": list(workspaces),
                "synced_total": engine.stats.synced, "ticks": engine.stats.ticks,
                "last_sync_at": engine.stats.last_sync_at, "last_error": engine.stats.last_error,
            })
            logger.log("INFO", "stop", "超级同步已停止")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
