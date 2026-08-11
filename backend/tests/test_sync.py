"""集成测试：跨 Agent 同步（plan + execute 两步铁律）。"""
from __future__ import annotations

import time


def test_sync_plan_and_execute(client):
    # plan
    res = client.post("/api/sync/plan", json={
        "src_agent": "alpha", "dst_agent": "beta", "files": ["SOUL.md", "AGENTS.md"],
    })
    assert res.status_code == 200
    plan = res.json()["data"]
    assert plan["src_agent"] == "alpha"
    assert plan["dst_agent"] == "beta"
    assert len(plan["files"]) == 2
    assert plan["files"][0]["path"] == "SOUL.md"
    assert "html_diff" in plan["files"][0]
    assert 0 <= plan["files"][0]["similarity"] <= 1

    # execute（确认子集：只同步 SOUL.md）
    res = client.post("/api/sync/execute", json={"plan_id": plan["plan_id"], "files": ["SOUL.md"]})
    assert res.status_code == 200
    results = res.json()["data"]["results"]
    assert len(results) == 1
    assert results[0]["file"] == "SOUL.md"
    assert results[0]["status"] == "ok"
    assert results[0]["backup_id"] is not None  # 写入前备份了 dst

    # dst 已被同步
    dst = client.get("/api/agents/beta/files/SOUL.md").json()["data"]["content"]
    assert "alpha SOUL" in dst

    # 审计记录
    audit = client.get("/api/audit", params={"action": "sync"}).json()["data"]
    assert any(e["target_path"] == "SOUL.md" and e["agent_id"] == "beta" for e in audit)


def test_sync_execute_without_plan_404(client):
    res = client.post("/api/sync/execute", json={"plan_id": "no-such-plan", "files": ["SOUL.md"]})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SYNC_PLAN_NOT_FOUND"


def test_sync_plan_expired(client, registry):
    res = client.post("/api/sync/plan", json={
        "src_agent": "alpha", "dst_agent": "beta", "files": ["SOUL.md"],
    })
    plan_id = res.json()["data"]["plan_id"]
    # 伪造 plan 过期
    entry = registry.sync.plans[plan_id]
    registry.sync.plans[plan_id] = (entry[0] - 31 * 60, entry[1])
    res = client.post("/api/sync/execute", json={"plan_id": plan_id, "files": ["SOUL.md"]})
    assert res.status_code == 410
    assert res.json()["error"]["code"] == "SYNC_PLAN_EXPIRED"
