"""集成测试：文档预设系统（M11 · Phase 2.5 Step 1）。

覆盖：内置预设播种 / CRUD / 系统预设保护 / version 自增 / apply plan + execute 两步流。
"""
from __future__ import annotations

from app.models.db import PresetRow, PresetVersionRow
from app.services.preset_service import (
    BUILTIN_PRESETS_REFRESHED,
    BUILTIN_PRESETS_RETIRED,
    PresetService,
)

BUILTIN_IDS = {
    "preset-soul-std", "preset-agents-std", "preset-mem-std",
    "preset-wlog-daily-std",
}


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


# ---------- 两类预设的边界（大模型专用 vs 主工作台用） ----------

def test_workbench_scope_excludes_daily_only_preset(client):
    """scope=workbench（文档预设页 / 主工作台应用预设）不返回大模型专用的 WORKLOG 预设。"""
    all_ids = {p["id"] for p in client.get("/api/presets").json()["data"]}
    assert "preset-wlog-daily-std" in all_ids  # 缺省仍返回全部：既有调用不受影响

    res = client.get("/api/presets", params={"scope": "workbench"})
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()["data"]}
    assert ids == BUILTIN_IDS - {"preset-wlog-daily-std"}

    # 反向：日志标准化界面按类型取，仍只看得到日志预设
    daily = client.get("/api/presets", params={"target_file_type": "WORKLOG"}).json()["data"]
    assert [p["id"] for p in daily] == ["preset-wlog-daily-std"]


def test_workbench_scope_hides_user_created_worklog_preset(client):
    """判据是「类型 = WORKLOG」，不是「内置与否」：用户自建的日志预设同样不进主工作台。"""
    client.post("/api/presets", json={
        "name": "我的日志预设",
        "target_file_type": "WORKLOG",
        "sections_json": [{"title": "一、概览", "required": True, "order": 1}],
    })
    workbench = client.get("/api/presets", params={"scope": "workbench"}).json()["data"]
    assert len(workbench) == 3   # 4 个内置预设里排除了 WORKLOG 那个
    assert all(p["target_file_type"] != "WORKLOG" for p in workbench)


def test_list_presets_invalid_scope(client):
    res = client.get("/api/presets", params={"scope": "nope"})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


def test_preset_exposes_is_builtin_source(client):
    """来源标识：内置预设 is_builtin=True、用户自建 False（M15 预设信息栏展示「来源」用）。"""
    builtin = client.get("/api/presets/preset-wlog-daily-std").json()["data"]
    assert builtin["is_builtin"] is True

    created = client.post("/api/presets", json={
        "name": "自建预设",
        "target_file_type": "MEMORY",
        "sections_json": [{"title": "一、概览", "required": True, "order": 1}],
    }).json()["data"]
    assert created["is_builtin"] is False
    assert client.get(f"/api/presets/{created['id']}").json()["data"]["is_builtin"] is False


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


# ---------- M15 规则载体：工作日志日标准化 ----------

def test_wlog_daily_std_preset_contract(client):
    """「工作日志日标准化」预设的契约来自 skill：章节含序号、WORKLOG、语义规则齐备。

    原「工作日志汇总」已并入本条（WORKLOG 只保留一个预设），故这里同时校验并进来的
    「五、明日计划」章节与归档顺序规则。
    """
    res = client.get("/api/presets/preset-wlog-daily-std")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["target_file_type"] == "WORKLOG"
    # 章节标题含序号：FormatValidator 对章节标题做精确匹配，序号不能丢
    assert [s["title"] for s in data["sections_json"]] == [
        "一、今日概览", "二、关键事件", "三、关键决策", "四、待办事项", "五、明日计划"]
    assert all(s["required"] is True for s in data["sections_json"])
    assert data["template_md"] and "section_order: strict" in data["template_md"]
    assert "- title: 五、明日计划" in data["template_md"]

    rules = " ".join(data["style_rules"])
    assert "默认不做敏感信息脱敏" in rules          # skill 的默认原则
    assert "Session Key" in rules                 # 低价值删除清单
    assert "未决问题与待办" in rules                # 高价值保留清单
    assert "对话腔" in rules                       # 客观改写要求
    assert "按时间倒序归档" in rules                # 原「工作日志汇总」的归档口径


def test_builtin_templates_match_sections_json():
    """每个内置预设的模板文档必填章节必须与其 sections 一致（两处文案不得漂移）。"""
    from app.services.preset_service import BUILTIN_PRESETS
    from app.services.preset_templates import BUILTIN_TEMPLATES
    from app.services.template_rules import parse_template

    for data in BUILTIN_PRESETS:
        template_md = BUILTIN_TEMPLATES.get(data["id"])
        assert template_md, f"{data['id']} 缺少内置模板文档"
        titles = [s["title"] for s in data["sections"]]
        parsed = [s.title for s in parse_template(template_md).required_sections]
        assert parsed == titles, f"{data['id']} 的模板章节与 sections 不一致"


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
    # 内置预设可删除；删除后不会被重新播种（仅首次空表全量播种 + 存量补种新增项）
    res = client.delete("/api/presets/preset-soul-std")
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True
    assert client.get("/api/presets/preset-soul-std").status_code == 404


def test_seed_builtins_backfills_new_preset_into_existing_install(registry):
    """存量安装（presets 表非空）升级后必须能看到本版本新增的内置预设。

    回归：此前 seed_builtins 仅在 presets 表为空时播种，新增内置预设
    进不了已存在的安装，P0 交付物在用户机器上不可见。
    """
    svc = registry.presets
    # 模拟「旧版本数据库」：新增预设那时还不存在（连同其版本快照一并清掉）
    with registry.db.session() as s:
        s.query(PresetVersionRow).filter(
            PresetVersionRow.preset_id == "preset-wlog-daily-std").delete()
        s.delete(s.get(PresetRow, "preset-wlog-daily-std"))
        s.commit()
    assert "preset-wlog-daily-std" not in {p.id for p in svc.list()}

    svc.seed_builtins()  # 模拟升级后启动

    assert svc.get("preset-wlog-daily-std").name == "工作日志日标准化"


def test_seed_builtins_does_not_revive_deleted_presets(registry):
    """用户主动删除的内置预设，重启后不得被塞回来（含本版本新增项）。"""
    svc = registry.presets
    svc.delete("preset-wlog-daily-std")  # 本版本新增项：补种过 → 快照即标记
    svc.delete("preset-soul-std")  # 历史内置预设：不在补种白名单

    svc.seed_builtins()  # 模拟下次启动

    ids = {p.id for p in svc.list()}
    assert "preset-wlog-daily-std" not in ids
    assert "preset-soul-std" not in ids


# ---------- 存量安装的内置预设迁移（刷新 / 退役）----------

def _seed_row(registry, preset_id: str, definition: dict, **overrides) -> None:
    """把一条内置预设写回成指定定义（模拟老版本数据库里的内容 / 用户改过的内容）。"""
    data = {**definition, "id": preset_id, **overrides}
    with registry.db.session() as s:
        row = s.get(PresetRow, preset_id)
        if row is None:
            s.add(PresetService._new_builtin_row(data))
        else:
            PresetService._apply_definition(row, data)
        s.commit()


def test_seed_builtins_refreshes_updated_builtin(registry):
    """存量安装上：内置预设内容有更新，且库里还是上一版发布的样子 → 自动升级。

    回归：此前进内置预设的改动只能影响全新安装，老机器永远拿不到修订。
    """
    svc = registry.presets
    _seed_row(registry, "preset-wlog-daily-std",
              BUILTIN_PRESETS_REFRESHED["preset-wlog-daily-std"])
    assert len(svc.get("preset-wlog-daily-std").sections_json) == 4

    svc.seed_builtins()  # 模拟升级后启动

    data = svc.get("preset-wlog-daily-std")
    assert [s.title for s in data.sections_json][-1] == "五、明日计划"
    assert "按时间倒序归档" in " ".join(data.style_rules)
    assert "- title: 五、明日计划" in (data.template_md or "")
    assert data.version == 2  # 升级留痕，不静默改内容


def test_seed_builtins_keeps_user_modified_builtin(registry):
    """存量安装上：用户改过的内置预设不得被升级覆盖。"""
    svc = registry.presets
    _seed_row(registry, "preset-wlog-daily-std",
              BUILTIN_PRESETS_REFRESHED["preset-wlog-daily-std"], name="我的日志规范")

    svc.seed_builtins()

    data = svc.get("preset-wlog-daily-std")
    assert data.name == "我的日志规范"
    assert len(data.sections_json) == 4  # 没有套上新的章节契约
    assert data.version == 1


def test_seed_builtins_retires_removed_builtin(registry):
    """存量安装上：已下线的内置预设（内容仍是最后一版）→ 从列表隐藏，行保留可取。"""
    svc = registry.presets
    _seed_row(registry, "preset-wlog-summary", BUILTIN_PRESETS_RETIRED["preset-wlog-summary"])
    assert "preset-wlog-summary" in {p.id for p in svc.list()}

    svc.seed_builtins()  # 模拟升级后启动

    assert "preset-wlog-summary" not in {p.id for p in svc.list()}
    # 行保留：历史批次 / AI 任务仍能按 id 取到它，不会 404
    assert svc.get("preset-wlog-summary").name == "工作日志汇总"


def test_seed_builtins_keeps_user_modified_removed_builtin(registry):
    """存量安装上：用户改过的「已下线」预设保留可见（不替用户做隐藏决定）。"""
    svc = registry.presets
    _seed_row(registry, "preset-wlog-summary", BUILTIN_PRESETS_RETIRED["preset-wlog-summary"],
              description="我自己改过的说明")

    svc.seed_builtins()

    assert "preset-wlog-summary" in {p.id for p in svc.list()}


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


# ---------- 「设为预设」：由当前文档生成预设 ----------

DOC = (
    "# SOUL.md\n\n"
    "## 核心行为准则\n\n- 简洁优先\n\n"
    "## 工作态度和原则\n\n- 先想后做\n\n"
    "## 学习与连续性\n\n- 记录演进\n\n"
    "## 核心边界\n\n- 隐私授权\n\n"
    "```markdown\n"
    "## 这是代码块里的假章节\n"
    "```\n"
)

BASE_BODY = {
    "name": "我的 SOUL 结构",
    "target_file_type": "SOUL",
    "content": DOC,
    "description": "由 main/SOUL.md 提取",
}


def _create_from_document(client, **overrides):
    return client.post("/api/presets/from-document", json={**BASE_BODY, **overrides})


def test_create_from_document_happy_path(client):
    res = _create_from_document(client)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["is_system"] is False
    assert data["version"] == 1
    assert data["name"] == "我的 SOUL 结构"
    assert data["target_file_type"] == "SOUL"
    assert data["description"] == "由 main/SOUL.md 提取"

    # 章节由模板 frontmatter 派生（代码块内的假章节不算）
    assert [s["title"] for s in data["sections_json"]] == [
        "核心行为准则", "工作态度和原则", "学习与连续性", "核心边界",
    ]
    assert all(s["required"] for s in data["sections_json"])

    # 模板正文即当前文档，规则按参数写入 frontmatter
    template = data["template_md"]
    assert template.startswith("---\n")
    assert "name: \"我的 SOUL 结构\"" in template
    assert "section_heading_level: 2" in template
    assert "section_order: strict" in template
    assert "frontmatter: optional" in template
    assert "# SOUL.md" in template and "## 核心行为准则" in template

    # 出现在预设列表中（4 内置 + 1 新建）
    listing = client.get("/api/presets").json()["data"]
    assert data["id"] in {p["id"] for p in listing}
    assert len(listing) == 5


def test_create_from_document_required_sections_subset(client):
    res = _create_from_document(client, required_sections=["核心行为准则", "核心边界"])
    assert res.status_code == 201
    data = res.json()["data"]
    # 顺序仍按文档出现顺序，未勾选的不进必填
    assert [s["title"] for s in data["sections_json"]] == ["核心行为准则", "核心边界"]


def test_create_from_document_heading_level_selectable(client):
    # 一级标题作为章节层级 → 仅 H1 入选
    res = _create_from_document(client, section_heading_level=1)
    assert res.status_code == 201
    assert [s["title"] for s in res.json()["data"]["sections_json"]] == ["SOUL.md"]

    # 文档中没有 ### → 400
    res = _create_from_document(client, section_heading_level=3)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"
    assert "未发现" in res.json()["error"]["message"]


def test_create_from_document_unknown_required_section_rejected(client):
    res = _create_from_document(client, required_sections=["不存在的章节"])
    assert res.status_code == 400
    assert "不存在" in res.json()["error"]["message"]


def test_create_from_document_too_large_rejected(client):
    res = _create_from_document(client, content="# T\n\n## 章节A\n\n" + "x" * (31 * 1024))
    assert res.status_code == 400
    assert "上限" in res.json()["error"]["message"]


def test_create_from_document_requires_frontmatter_flag(client):
    res = _create_from_document(client, require_frontmatter=True)
    assert res.status_code == 201
    assert "frontmatter: required" in res.json()["data"]["template_md"]


def test_create_from_document_with_loose_order(client):
    res = _create_from_document(client, section_order="loose")
    assert res.status_code == 201
    assert "section_order: loose" in res.json()["data"]["template_md"]


def test_generated_preset_is_applicable(client):
    """生成的预设可立即用于「应用预设」：缺失章节被补齐、格式校验通过。"""
    pid = _create_from_document(client, required_sections=["核心行为准则", "核心边界"]).json()["data"]["id"]

    plan = client.post(f"/api/presets/{pid}/apply", json={
        "agent_id": "alpha", "file_path": "MEMORY.md",
    }).json()["data"]
    assert "## 核心行为准则" in plan["proposed_content"]
    assert "## 核心边界" in plan["proposed_content"]
    assert plan["format_report"]["ok"] is True

