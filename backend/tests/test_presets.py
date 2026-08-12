"""集成测试：文档预设系统（M11 · Phase 2.5 Step 1）。

覆盖：内置预设播种 / CRUD / 系统预设保护 / version 自增 / apply plan + execute 两步流。
"""
from __future__ import annotations


BUILTIN_IDS = {"preset-soul-std", "preset-agents-std", "preset-mem-std", "preset-wlog-summary"}


# ---------- 列表 / 过滤 ----------

def test_list_presets_has_4_builtins(client):
    res = client.get("/api/presets")
    assert res.status_code == 200
    presets = res.json()["data"]
    assert len(presets) == 4
    assert {p["id"] for p in presets} == BUILTIN_IDS
    assert all(p["version"] == 1 for p in presets)


def test_list_presets_filter_by_target_type(client):
    res = client.get("/api/presets", params={"target_file_type": "SOUL"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == "preset-soul-std"


def test_list_presets_invalid_target_type(client):
    res = client.get("/api/presets", params={"target_file_type": "NOPE"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


# ---------- 创建 / 详情 ----------

def test_create_user_preset(client):
    res = client.post("/api/presets", json={
        "name": "AGENTS 老板风格",
        "target_file_type": "AGENTS",
        "description": "符合老板偏好的结构",
        "sections_json": [
            {"title": "首次运行", "required": True, "order": 1},
            {"title": "会话启动", "required": True, "order": 2},
        ],
        "frontmatter_json": {"schema": "soulforge.preset/v1", "owner": "user"},
        "style_rules": ["emoji-in-section-title=false", "口语化禁令"],
    })
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["is_system"] is False
    assert data["version"] == 1
    assert len(data["sections_json"]) == 2

    # 出现在列表中（4 内置 + 1 用户）
    listing = client.get("/api/presets").json()["data"]
    assert len(listing) == 5


def test_get_preset_detail(client):
    res = client.get("/api/presets/preset-soul-std")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "SOUL 标准结构"
    assert len(data["sections_json"]) == 4
    assert data["sections_json"][0]["title"] == "核心行为准则"
    assert data["sections_json"][0]["required"] is True
    assert data["style_rules"]
    assert data["frontmatter_json"]["schema"] == "soulforge.preset/v1"


def test_get_preset_not_found(client):
    res = client.get("/api/presets/preset-nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRESET_NOT_FOUND"


# ---------- 更新 / version 自增 ----------

def test_update_user_preset_increments_version(client):
    created = client.post("/api/presets", json={
        "name": "用户预设", "target_file_type": "ANY",
        "sections_json": [{"title": "章节A", "required": True, "order": 1}],
    }).json()["data"]
    pid = created["id"]

    res = client.put(f"/api/presets/{pid}", json={"name": "用户预设 v2"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["version"] == 2
    assert data["name"] == "用户预设 v2"
    assert len(data["sections_json"]) == 1  # 未传字段保持不变


def test_update_builtin_preset_full_fields(client):
    # 内置预设与普通预设一致：可修改全部字段
    res = client.put("/api/presets/preset-soul-std", json={
        "name": "SOUL 标准结构（自定义版）",
        "sections_json": [{"title": "我的章节", "required": True, "order": 1}],
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["version"] == 2
    assert data["name"] == "SOUL 标准结构（自定义版）"
    assert len(data["sections_json"]) == 1


def test_update_builtin_preset_partial(client):
    res = client.put("/api/presets/preset-soul-std", json={
        "description": "新描述",
        "style_rules": ["规则1", "规则2"],
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["version"] == 2
    assert data["description"] == "新描述"
    assert data["style_rules"] == ["规则1", "规则2"]
    assert len(data["sections_json"]) == 4  # 未传字段保持不变


# ---------- 删除 ----------

def test_delete_builtin_preset_allowed(client):
    # 内置预设可删除；删除后不会被重新播种（仅首次空表时播种）
    res = client.delete("/api/presets/preset-soul-std")
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True
    assert client.get("/api/presets/preset-soul-std").status_code == 404


def test_delete_user_preset(client):
    created = client.post("/api/presets", json={
        "name": "待删除", "target_file_type": "ANY",
    }).json()["data"]
    pid = created["id"]

    res = client.delete(f"/api/presets/{pid}")
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True

    assert client.get(f"/api/presets/{pid}").status_code == 404


# ---------- 应用（plan + execute 两步流） ----------

def test_apply_plan_appends_missing_sections(client):
    res = client.post("/api/presets/preset-soul-std/apply", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
    })
    assert res.status_code == 200
    plan = res.json()["data"]
    assert plan["agent_id"] == "alpha"
    assert plan["file_path"] == "SOUL.md"
    assert plan["preset_id"] == "preset-soul-std"
    # 原文件没有内置预设的任何章节 → 全部补齐
    assert "## 核心行为准则" in plan["proposed_content"]
    assert "## 核心边界" in plan["proposed_content"]
    # 原始内容被保留
    assert "原则：诚实。" in plan["proposed_content"]
    assert plan["unified_diff"]
    assert isinstance(plan["lint_warnings"], list)


def test_apply_plan_no_change_when_all_sections_present(client):
    # 先写入一个已含全部章节的文件
    content = "# SOUL.md\n\n## 核心行为准则\n\n简洁\n\n## 工作态度和原则\n\n先想后做\n\n## 学习与连续性\n\n记录\n\n## 核心边界\n\n隐私"
    client.put("/api/agents/alpha/files/SOUL.md", json={"content": content})
    res = client.post("/api/presets/preset-soul-std/apply", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
    })
    plan = res.json()["data"]
    assert plan["proposed_content"] == plan["current_snapshot"]
    assert plan["unified_diff"] == ""


def test_apply_plan_missing_file(client):
    res = client.post("/api/presets/preset-soul-std/apply", json={
        "agent_id": "alpha", "file_path": "memory/nope.md",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_apply_plan_unknown_preset(client):
    res = client.post("/api/presets/preset-nope/apply", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRESET_NOT_FOUND"


def test_apply_execute_writes_with_backup_and_audit(client):
    plan = client.post("/api/presets/preset-soul-std/apply", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
    }).json()["data"]

    res = client.post("/api/presets/preset-soul-std/apply/execute", json={
        "plan_id": plan["plan_id"], "agent_id": "alpha", "file_path": "SOUL.md",
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["backup_id"] is not None
    assert data["file_size"] > 0

    # 文件内容已更新
    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "## 核心行为准则" in content

    # 审计日志有 preset_apply 记录
    audit = client.get("/api/audit").json()["data"]
    actions = [a["action"] for a in audit]
    assert "preset_apply" in actions


def test_apply_execute_plan_not_found(client):
    res = client.post("/api/presets/preset-soul-std/apply/execute", json={
        "plan_id": "no-such-plan", "agent_id": "alpha", "file_path": "SOUL.md",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRESET_PLAN_NOT_FOUND"


def test_apply_execute_mismatched_target(client):
    plan = client.post("/api/presets/preset-soul-std/apply", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
    }).json()["data"]
    res = client.post("/api/presets/preset-soul-std/apply/execute", json={
        "plan_id": plan["plan_id"], "agent_id": "beta", "file_path": "SOUL.md",
    })
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


def test_apply_execute_consumes_plan(client):
    # 计划执行成功后即失效，不能复用（防重复写入）
    plan = client.post("/api/presets/preset-soul-std/apply", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
    }).json()["data"]
    body = {"plan_id": plan["plan_id"], "agent_id": "alpha", "file_path": "SOUL.md"}
    assert client.post("/api/presets/preset-soul-std/apply/execute", json=body).status_code == 200
    res = client.post("/api/presets/preset-soul-std/apply/execute", json=body)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRESET_PLAN_NOT_FOUND"


# ---------- 版本历史（在线编辑 · 历史回溯） ----------

def test_create_and_update_save_version_snapshots(client):
    created = client.post("/api/presets", json={
        "name": "历史测试", "target_file_type": "ANY",
        "sections_json": [{"title": "章节A", "required": True, "order": 1}],
    }).json()["data"]
    pid = created["id"]

    versions = client.get(f"/api/presets/{pid}/versions").json()["data"]
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["name"] == "历史测试"

    client.put(f"/api/presets/{pid}", json={"name": "历史测试 v2"})
    versions = client.get(f"/api/presets/{pid}/versions").json()["data"]
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["name"] == "历史测试 v2"
    assert versions[1]["name"] == "历史测试"


def test_restore_version_rolls_back_and_increments(client):
    created = client.post("/api/presets", json={
        "name": "回滚测试", "target_file_type": "AGENTS",
        "sections_json": [{"title": "章节1", "required": True, "order": 1}],
        "style_rules": ["规则1"],
    }).json()["data"]
    pid = created["id"]

    client.put(f"/api/presets/{pid}", json={"name": "回滚测试 v2", "style_rules": ["规则2", "规则3"]})
    versions = client.get(f"/api/presets/{pid}/versions").json()["data"]
    v1 = next(v for v in versions if v["version"] == 1)

    res = client.post(f"/api/presets/{pid}/versions/{v1['id']}/restore")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "回滚测试"
    assert data["style_rules"] == ["规则1"]
    assert data["version"] == 3  # v1 快照 +1

    versions = client.get(f"/api/presets/{pid}/versions").json()["data"]
    assert len(versions) == 3


def test_list_versions_preset_not_found(client):
    res = client.get("/api/presets/preset-nope/versions")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRESET_NOT_FOUND"


def test_restore_version_not_found(client):
    created = client.post("/api/presets", json={
        "name": "x", "target_file_type": "ANY",
    }).json()["data"]
    res = client.post(f"/api/presets/{created['id']}/versions/99999/restore")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRESET_NOT_FOUND"


def test_apply_plan_on_new_file_rejected(client):
    # 预设应用针对既有文件的「重整」：文件不存在 → 404，不创建空文件
    res = client.post("/api/presets/preset-mem-std/apply", json={
        "agent_id": "alpha", "file_path": "memory/new.md",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "FILE_NOT_FOUND"
