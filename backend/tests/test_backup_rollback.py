"""集成测试：备份 / 回滚（备份流程必须有集成测试）。"""
from __future__ import annotations

from pathlib import Path


def test_write_creates_auto_backup(client, openclaw_dir: Path):
    """写入前自动备份：改 SOUL.md 后应出现 .bak 文件 + history 记录。"""
    res = client.get("/api/agents/alpha/files/SOUL.md")
    old_sha = res.json()["data"]["sha256"]

    res = client.put("/api/agents/alpha/files/SOUL.md", json={"content": "# alpha SOUL\n\n原则：诚实。\n新增一行。\n"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["backup_id"] is not None
    assert data["sha256"] != old_sha

    # 备份物理文件存在
    backup_dir = openclaw_dir.parent / "soulforge-data" / "backups" / "alpha" / "SOUL.md"
    assert any(backup_dir.glob("SOUL.md.*.bak"))

    # history API 有记录
    res = client.get("/api/agents/alpha/files/SOUL.md/history")
    history = res.json()["data"]
    assert len(history) >= 1
    assert history[0]["reason"] == "auto-write"
    assert history[0]["sha256"] == old_sha


def test_rollback_restores_and_keeps_current(client, openclaw_dir: Path):
    """回滚：先备份当前（pre-rollback）再写入历史版本。"""
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "# alpha SOUL\n\nv2 内容\n"})
    history = client.get("/api/agents/alpha/files/SOUL.md/history").json()["data"]
    backup_id = history[0]["backup_id"]  # v1（原始）的备份

    res = client.post(f"/api/backups/alpha/SOUL.md/rollback", json={"backup_id": backup_id})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["rolled_back_to"] == backup_id
    assert data["new_backup_id"] > 0  # 当前状态已备份

    # 内容已回滚
    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "alpha SOUL" in content and "v2 内容" not in content

    # pre-rollback 备份存在
    history = client.get("/api/agents/alpha/files/SOUL.md/history").json()["data"]
    reasons = [h["reason"] for h in history]
    assert "pre-rollback" in reasons


def test_optimistic_lock_conflict(client):
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "新版本\n"})
    sha = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["sha256"]
    # 用错误的 expected_sha256 → 409
    res = client.put("/api/agents/alpha/files/SOUL.md",
                     json={"content": "冲突写入\n", "expected_sha256": "deadbeef"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"
    # 正确 hash → 成功
    res = client.put("/api/agents/alpha/files/SOUL.md",
                     json={"content": "成功写入\n", "expected_sha256": sha})
    assert res.status_code == 200


def test_list_backups_grouped(client):
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "内容 A\n"})
    client.put("/api/agents/alpha/files/AGENTS.md", json={"content": "内容 B\n"})
    res = client.get("/api/backups/alpha")
    assert res.status_code == 200
    files = res.json()["data"]["files"]
    paths = {f["file_path"] for f in files}
    assert "SOUL.md" in paths
    assert "AGENTS.md" in paths


def test_delete_goes_to_trash(client, openclaw_dir: Path):
    """删除走 send2trash（可恢复），文件从列表消失。"""
    target = openclaw_dir / "workspace-alpha" / "temp_delete_me.md"
    target.write_text("# 待删除\n", encoding="utf-8")
    res = client.delete("/api/agents/alpha/files/temp_delete_me.md")
    assert res.status_code == 200
    assert not target.exists()
    files = client.get("/api/agents/alpha/files").json()["data"]
    assert all(f["path"] != "temp_delete_me.md" for f in files)
