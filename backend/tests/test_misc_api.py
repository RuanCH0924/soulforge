"""集成测试：模板系统 / diff / 统计 / lint API / 跨 Agent 编辑 / 审计。"""
from __future__ import annotations

from pathlib import Path


# ---------- 模板 ----------

def test_list_templates(client):
    res = client.get("/api/templates")
    assert res.status_code == 200
    templates = res.json()["data"]
    ids = {t["id"] for t in templates}
    assert {"standard", "minimal", "lawyer-agent", "writer-agent"} <= ids
    std = next(t for t in templates if t["id"] == "standard")
    assert std["file_count"] >= 8


def test_apply_template(client, tmp_path: Path):
    target = tmp_path / "new-agent-workspace"
    res = client.post("/api/templates/apply", json={
        "template_id": "minimal",
        "new_agent_id": "gamma",
        "target_workspace": str(target),
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agent_id"] == "gamma"
    assert len(data["files_created"]) == 2
    assert (target / "AGENTS.md").is_file()
    assert (target / "IDENTITY.md").is_file()


def test_apply_template_not_found(client):
    res = client.post("/api/templates/apply", json={
        "template_id": "nope", "new_agent_id": "gamma", "target_workspace": "x",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


# ---------- Diff ----------

def test_diff_between_agents(client):
    res = client.get("/api/diff", params={"a": "alpha", "b": "beta", "file": "SOUL.md"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agent_a"] == "alpha"
    assert data["agent_b"] == "beta"
    assert 0 <= data["similarity"] <= 1
    assert data["unified_diff"]
    assert "diff-view" in data["html_diff"]


def test_diff_history(client):
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "# alpha SOUL\n\n新版内容\n"})
    history = client.get("/api/agents/alpha/files/SOUL.md/history").json()["data"]
    backup_id = history[0]["backup_id"]
    res = client.get("/api/diff/history", params={"agent": "alpha", "file": "SOUL.md", "against": backup_id})
    assert res.status_code == 200
    assert res.json()["data"]["file"] == "SOUL.md"


# ---------- 统计 ----------

def test_stats(client):
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agents_total"] == 2
    assert data["files_total"] >= 8
    assert data["core_files"] >= 6
    assert data["memory_files"] >= 1
    assert data["backup_total"] == 0


# ---------- Lint API ----------

def test_lint_agent_api(client):
    res = client.get("/api/lint/alpha")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agent_id"] == "alpha"
    assert "stats" in data
    assert data["stats"]["files_checked"] >= 6


def test_lint_file_api(client):
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "# SOUL\n\n*最后更新：2026-08-06*\n"})
    res = client.get("/api/lint/file/alpha/SOUL.md")
    assert res.status_code == 200
    warnings = res.json()["data"]["warnings"]
    assert any(w["rule_id"] == "L4-TIMESTAMP" for w in warnings)


def test_lint_all(client):
    res = client.get("/api/lint/all")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agents"] == 2


def test_lint_strict_mode_blocks_save(client, registry):
    """严格模式：违规内容阻止保存（409）。"""
    registry.config.lint.strict_mode = True
    res = client.put("/api/agents/alpha/files/SOUL.md",
                     json={"content": "# SOUL\n\n*最后修订：2026-08-06*\n"})
    assert res.status_code == 409
    # 文件未被修改
    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "最后修订" not in content
    registry.config.lint.strict_mode = False


# ---------- 跨 Agent 编辑 ----------

def test_cross_write(client):
    res = client.post("/api/agents/files/cross-write", json={
        "files": [
            {"agent_id": "alpha", "path": "MEMORY.md"},   # alpha 已有 MEMORY.md → 会备份
            {"agent_id": "beta", "path": "MEMORY.md"},    # beta 无 MEMORY.md → 新文件无备份
        ],
        "content": "# MEMORY\n\n统一规则：跨 Agent 同步测试。\n",
    })
    assert res.status_code == 200
    results = res.json()["data"]["results"]
    assert len(results) == 2
    assert results[0]["backup_id"] is not None  # 已有文件写入前自动备份
    assert results[1]["backup_id"] is None      # 新文件无需备份
    assert "统一规则" in client.get("/api/agents/beta/files/MEMORY.md").json()["data"]["content"]


# ---------- 审计 ----------

def test_audit_trail(client):
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": "# alpha SOUL\n\n审计测试\n"})
    audit = client.get("/api/audit").json()["data"]
    assert any(e["action"] == "write" and e["agent_id"] == "alpha" and e["target_path"] == "SOUL.md" for e in audit)
