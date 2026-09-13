"""集成 + 单元测试：超级同步（独立脚本 / 配置 / 状态 / 日志 / 引擎）。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from app.services import super_sync_common as ssc
from app.services.super_sync_engine import SuperSyncEngine


# ---------------------------------------------------------------- 配置


def test_config_default_and_update(client):
    data = client.get("/api/super-sync/config").json()["data"]
    assert data["agents"] == []
    assert data["files"] == {}
    assert data["retention_days"] >= 30  # 留存不得少于 30 天

    res = client.put("/api/super-sync/config", json={
        "agents": ["alpha", "beta"],
        "files": {"alpha": ["SOUL.md", "AGENTS.md"], "beta": ["SOUL.md"]},
        "interval_seconds": 1,
    })
    assert res.status_code == 200
    cfg = res.json()["data"]
    assert cfg["agents"] == ["alpha", "beta"]
    assert cfg["files"]["alpha"] == ["AGENTS.md", "SOUL.md"]  # 已排序去重
    # 持久化：重新读取一致
    assert client.get("/api/super-sync/config").json()["data"] == cfg


def test_config_retention_clamped_to_minimum():
    normalized = ssc.normalize_config({"retention_days": 3, "agents": [], "files": {}})
    assert normalized["retention_days"] == ssc.MIN_RETENTION_DAYS


def test_config_only_allows_core_documents(client):
    """同步文档限定为 5 个核心文档，其余（含子目录 / 私有文件）一律被丢弃。"""
    res = client.put("/api/super-sync/config", json={
        "agents": ["alpha", "beta"],
        "files": {
            "alpha": ["SOUL.md", "notes/plan.md", "private.md", "MEMORY.md"],
            "beta": ["SOUL.md", "AGENTS.md", "IDENTITY.md"],
        },
    })
    assert res.status_code == 200
    files = res.json()["data"]["files"]
    assert files["alpha"] == ["MEMORY.md", "SOUL.md"]
    assert files["beta"] == ["AGENTS.md", "IDENTITY.md", "SOUL.md"]
    # 白名单常量与需求一致
    assert ssc.SYNC_FILENAMES == ("SOUL.md", "AGENTS.md", "USER.md", "MEMORY.md", "IDENTITY.md")


# ---------------------------------------------------------------- 状态


def test_status_stopped_when_not_running(client):
    status = client.get("/api/super-sync/status").json()["data"]
    assert status["state"] == "stopped"
    assert status["synced_total"] == 0


# ---------------------------------------------------------------- 日志


def test_logs_query_filter_and_export(client, registry):
    log_dir = ssc.log_dir(registry.config.data_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {"ts": "2026-09-13T10:00:00.000", "ts_unix": 1000, "level": "INFO",
         "event": "sync", "path": "SOUL.md", "result": "ok"},
        {"ts": "2026-09-13T10:00:01.000", "ts_unix": 1001, "level": "ERROR",
         "event": "sync", "path": "A.md", "result": "failed", "error": "boom"},
    ]
    (log_dir / "super_sync-20260913.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8",
    )

    # 按级别筛选
    filtered = client.get("/api/super-sync/logs", params={"levels": "ERROR"}).json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["level"] == "ERROR"

    # 时间范围筛选
    ranged = client.get("/api/super-sync/logs", params={"since": 1001}).json()["data"]
    assert ranged["total"] == 1 and ranged["items"][0]["path"] == "A.md"

    # 导出仅含 INFO
    exported = client.get("/api/super-sync/logs/export", params={"levels": "INFO"})
    assert exported.status_code == 200
    assert b"SOUL.md" in exported.content
    assert b"A.md" not in exported.content

    # 非法级别
    bad = client.get("/api/super-sync/logs", params={"levels": "NOPE"})
    assert bad.status_code == 400


# ---------------------------------------------------------------- 引擎


def _write(path: Path, content: str, *, newer: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if newer:
        ts = time.time() + newer
        import os

        os.utime(path, (ts, ts))


def test_engine_syncs_newest_and_respects_scope(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    (a / "SOUL.md").parent.mkdir(parents=True, exist_ok=True)
    _write(a / "SOUL.md", "v1")
    _write(b / "SOUL.md", "v2", newer=10)  # b 最新 → 作为源
    _write(c / "SOUL.md", "v3")            # c 未选中，绝不能被改动
    _write(a / "AGENTS.md", "only-a")      # 未选中文件
    _write(a / ".hidden.md", "secret")     # 隐藏文件

    config = {
        "agents": ["a", "b"],
        "files": {"a": ["SOUL.md", ".hidden.md"], "b": ["SOUL.md"]},
        "interval_seconds": 1,
    }
    engine = SuperSyncEngine({"a": a, "b": b}, config)
    actions = engine.sync_once()

    assert len(actions) == 1
    assert actions[0].source_agent == "b" and actions[0].target_agent == "a"
    assert actions[0].result == "ok"
    assert actions[0].diff and "v2" in actions[0].diff
    assert (a / "SOUL.md").read_text(encoding="utf-8") == "v2"
    assert (c / "SOUL.md").read_text(encoding="utf-8") == "v3"  # 未选中 Agent 不受影响
    assert (a / "AGENTS.md").read_text(encoding="utf-8") == "only-a"  # 未选中文件不受影响

    # 内容已一致 → 第二轮无动作（避免回声循环）
    assert engine.sync_once() == []


def test_engine_skips_file_present_in_single_agent(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a / "ONLY_A.md", "x")
    config = {"agents": ["a", "b"], "files": {"a": ["ONLY_A.md"], "b": ["ONLY_A.md"]}, "interval_seconds": 1}
    engine = SuperSyncEngine({"a": a, "b": b}, config)
    assert engine.sync_once() == []
    assert not (b / "ONLY_A.md").exists()  # 不凭空创建缺失文件


def test_engine_run_completes_sync_within_seconds(tmp_path):
    """秒级实时性：修改后 3 秒内完成同步。"""
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a / "SOUL.md", "same")
    _write(b / "SOUL.md", "same")
    config = {"agents": ["a", "b"], "files": {"a": ["SOUL.md"], "b": ["SOUL.md"]}, "interval_seconds": 1}
    engine = SuperSyncEngine({"a": a, "b": b}, config)

    stop = threading.Event()
    thread = threading.Thread(target=engine.run, args=(stop,), kwargs={"interval_seconds": 0.5}, daemon=True)
    thread.start()
    try:
        time.sleep(0.3)
        _write(a / "SOUL.md", "changed-content-123")
        deadline = time.time() + 3
        synced = False
        while time.time() < deadline:
            if (b / "SOUL.md").read_text(encoding="utf-8") == "changed-content-123":
                synced = True
                break
            time.sleep(0.1)
        assert synced, "3 秒内未完成同名文件同步"
    finally:
        stop.set()
        thread.join(timeout=2)
