"""集成测试：diff / 统计 / lint API / 跨 Agent 编辑 / 审计。"""
from __future__ import annotations


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


def test_stats_does_not_report_lint_count(client):
    """统计接口不得返回 lint 警告数（防止再出现「面板恒为 0、检查报告几百条」的口径冲突）。

    该指标只能实时跑 lint 得到（`files.lint_warnings` 从不被扫描填充），
    UI 统一取自 `GET /api/lint/all`——与「检查报告」同源同口径。
    """
    stats = client.get("/api/stats").json()["data"]
    assert "lint_warnings_total" not in stats

    # 同一时刻两个来源给出同一个数：/api/lint/all 的逐条之和
    results = client.get("/api/lint/all").json()["data"]["results"]
    total = sum(len(r["warnings"]) for r in results)
    assert total == sum(r["stats"]["warnings"] + r["stats"]["errors"] for r in results)


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


def test_lint_rules_catalog(client):
    """规则目录：8 条规则齐备，且每项都带展示所需的说明与作用域。"""
    res = client.get("/api/lint/rules")
    assert res.status_code == 200
    data = res.json()["data"]
    rules = data["rules"]
    assert data["count"] == len(rules) == 8
    assert {r["rule_id"] for r in rules} == {
        "L4-TIMESTAMP", "L4-VERSION", "L4-NARRATIVE", "BOUNDARY-VIOLATE",
        "EMPTY-FILE", "LARGE-FILE", "CORE-MISSING", "CROSS-AGENT-DRIFT",
    }
    for r in rules:
        assert r["description"], f"{r['rule_id']} 缺少规则说明"
        assert r["scope"] in {"file", "agent"}
        assert r["severity"] in {"warning", "error"}
    # 作用域归类：两条 Agent 级规则需读 Agent 全貌
    by_scope = {r["rule_id"]: r["scope"] for r in rules}
    assert by_scope["CORE-MISSING"] == "agent"
    assert by_scope["CROSS-AGENT-DRIFT"] == "agent"
    assert by_scope["L4-TIMESTAMP"] == "file"


def test_lint_rules_catalog_matches_executed_rules(client, registry):
    """目录与真正执行的规则集合一致（防止新增规则只加检查、忘了登记）。"""
    executed = {r.rule_id for r in [*registry.lint.file_rules, *registry.lint.agent_rules]}
    cataloged = {r.rule_id for r in registry.lint.rule_catalog()}
    assert cataloged == executed


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
