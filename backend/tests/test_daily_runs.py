"""集成测试：工作日志标准化批次（M15 · P2）。

覆盖方案 §7.3 的安全与破坏性测试 + §6.2 的运行流程：
正常流程（创建 → 生成 → 确认 → 写入 → 删碎片 → 验收）/ 幂等复用 / 并发 409 /
路径穿越 403 / 写前验收不过 → 零污染 / 碎片删失败 → partially_applied /
跳过与拒绝 / 空范围 / 天数上限 / 全局 dry-run 开关。
LLM 全部 mock；**每一步都核对磁盘真实状态**。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from app.core.errors import ConflictError
from app.services import daily_run_service as drs
from app.services.llm_registry import LLMResponse, LLMTokenUsage

PROVIDER = {
    "id": "run-test-provider",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-test-000",
    "model": "gpt-4o",
    "protocol": "openai-completions",
}
PRESET_ID = "preset-wlog-daily-std"

CALLS: list[list[dict]] = []
OUTPUT_OVERRIDE: list[str | None] = [None]
# 按日期指定输出（多日批次里需要逐日不同输出时用），优先级高于 OUTPUT_OVERRIDE
OUTPUT_OVERRIDE_BY_DAY: dict[str, str] = {}
_PROMPT_DATE_RE = re.compile(r"【任务】把 (\d{4}-\d{2}-\d{2}) 这一天")


def _doc(date: str, extra: str = "") -> str:
    return (
        f"# 工作日志 - {date}\n\n"
        "## 一、今日概览\n\n"
        "- **日期**：" + date + "\n"
        "- **核心活动**：端口仪表盘刷新完成\n\n"
        "## 二、关键事件\n\n"
        "### 事件 1\n\n"
        "- 事实：22 个端口、RSS 总 2832 MB\n"
        "- 结果：tdai-gateway 涨到 467MB\n\n"
        "## 三、关键决策\n\n"
        "| 决策项 | 内容 |\n"
        "|--------|------|\n"
        "| 8420 水位 | 纳入观察 |\n\n"
        "## 四、待办事项\n\n"
        "- [ ] 复核 8420 GC 后水位\n\n"
        "## 五、明日计划\n\n"
        "- 观察 8420 GC 后水位\n"
        + extra
    )


async def _fake_chat(self, messages, max_tokens=None, temperature=None):
    CALLS.append(messages)
    user = messages[-1]["content"]
    match = _PROMPT_DATE_RE.search(user)
    date = match.group(1) if match else _CURRENT_DATE[0]
    if date in OUTPUT_OVERRIDE_BY_DAY:
        content = OUTPUT_OVERRIDE_BY_DAY[date]
    elif OUTPUT_OVERRIDE[0] is not None:
        content = OUTPUT_OVERRIDE[0]
    else:
        content = _doc(_CURRENT_DATE[0])
    return LLMResponse(
        content=content,
        usage=LLMTokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate_usd=0.0025,
    )


_CURRENT_DATE: list[str] = [""]


@pytest.fixture()
def prepared(client, registry, monkeypatch):
    client.post("/api/llm/providers", json=PROVIDER)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat)
    CALLS.clear()
    OUTPUT_OVERRIDE[0] = None
    OUTPUT_OVERRIDE_BY_DAY.clear()
    return client, registry


def _root(registry) -> Path:
    return Path(registry.discovery.require("alpha").workspace)


def _write(registry, rel: str, content: str) -> Path:
    full = _root(registry) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


def _create(client, date_from: str, date_to: str, **over):
    body = {"agent_id": "alpha", "date_from": date_from, "date_to": date_to,
            "preset_id": PRESET_ID, "provider_id": PROVIDER["id"]}
    body.update(over)
    return client.post("/api/daily-runs", json=body)


def _wait_run(client, run_id: str, timeout: float = 5.0) -> dict:
    """等后台逐日生成结束（planned → awaiting_confirm / failed / empty）。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/daily-runs/{run_id}").json()["data"]
        if last["status"] != drs.RUN_PLANNED:
            return last
        time.sleep(0.05)
    raise AssertionError(f"批次 {run_id} 未在 {timeout}s 内结束：{last and last['status']}")


def _seed_multi_source_day(registry, date: str) -> tuple[Path, Path]:
    """造一个「同日多来源」的日子：A 主文件 + B session 导出。"""
    a = _write(registry, f"memory/{date}.md", f"# {date}\n\n- 主骨架事实：日常巡检完成\n")
    b = _write(registry, f"memory/{date}-1415.md", (
        "# Session: " + date + " 14:15:00 Asia/Shanghai\n\n"
        "- **Session Key**: agent:alpha:main\n"
        "- **Source**: gateway:sessions.reset\n\n"
        "assistant: \"端口仪表盘已刷新：22 个端口、RSS 总 2832 MB。\"\n"))
    return a, b


# ---------- 正常流程 ----------


def test_full_flow_create_confirm_apply_then_report(prepared):
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-01")
    _CURRENT_DATE[0] = "2026-11-01"

    created = _create(client, "2026-11-01", "2026-11-01").json()["data"]
    assert created["status"] == drs.RUN_PLANNED
    assert created["days_total"] == 1
    assert created["reused"] is False

    run = _wait_run(client, created["run_id"])
    assert run["status"] == drs.RUN_AWAITING
    item = run["items"][0]
    assert item["status"] == drs.ITEM_PLANNED
    assert item["has_standard"] is True
    assert item["fragments_to_delete"] == ["memory/2026-11-01-1415.md"]
    assert item["format_report"]["ok"] is True
    assert item["html_diff"] and "<" in item["html_diff"]
    assert run["tokens_used"] == 150

    # 未确认前：一个字节都没动
    assert a_path.read_text(encoding="utf-8").startswith("# 2026-11-01")
    assert b_path.exists()

    applied = client.post(f"/api/daily-runs/{created['run_id']}/apply",
                          json={"apply_all": True}).json()["data"]
    assert applied["applied"] == ["2026-11-01"]
    assert applied["status"] == drs.RUN_APPLIED

    # 日文件已按标准结构改写 + 碎片已删（走回收站，磁盘上不可见）
    content = a_path.read_text(encoding="utf-8")
    assert content.startswith("# 工作日志 - 2026-11-01")
    assert "## 一、今日概览" in content and "## 四、待办事项" in content
    assert not b_path.exists()

    report = client.get(f"/api/daily-runs/{created['run_id']}/report").json()["data"]
    assert report["passed"] is True
    assert report["days_delivered"] == 1
    entry = report["items"][0]
    assert entry["single_file"] and entry["naming_ok"] and entry["sections_ok"]
    assert entry["no_residue"] and entry["fragments_gone"]


def test_apply_writes_backup_and_audit(prepared):
    client, registry = prepared
    _seed_multi_source_day(registry, "2026-11-02")
    _CURRENT_DATE[0] = "2026-11-02"
    run_id = _create(client, "2026-11-02", "2026-11-02").json()["data"]["run_id"]
    _wait_run(client, run_id)

    client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})

    detail = client.get(f"/api/daily-runs/{run_id}").json()["data"]
    assert detail["items"][0]["backup_id"]                   # 写前自动备份
    actions = [a["action"] for a in client.get("/api/audit", params={"limit": 50}).json()["data"]]
    assert "daily_run_create" in actions and "daily_apply" in actions


# ---------- 幂等 ----------


def test_same_scope_same_content_reuses_run(prepared):
    client, registry = prepared
    _seed_multi_source_day(registry, "2026-11-03")
    _CURRENT_DATE[0] = "2026-11-03"

    first = _create(client, "2026-11-03", "2026-11-03").json()["data"]
    _wait_run(client, first["run_id"])
    calls_after_first = len(CALLS)

    second = _create(client, "2026-11-03", "2026-11-03").json()["data"]
    assert second["reused"] is True
    assert second["run_id"] == first["run_id"]
    assert len(CALLS) == calls_after_first      # 没有第二次 LLM 调用


# ---------- 并发：乐观锁 409 ----------


def test_apply_conflicts_when_target_changed_after_plan(prepared):
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-04")
    _CURRENT_DATE[0] = "2026-11-04"
    run_id = _create(client, "2026-11-04", "2026-11-04").json()["data"]["run_id"]
    _wait_run(client, run_id)

    # 计划生成后，目标文件被外部改动（等价于「另一个批次抢先确认」）
    a_path.write_text("# 2026-11-04\n\n- 外部新内容\n", encoding="utf-8")

    res = client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})
    assert res.status_code == 409
    detail = res.json()["error"]
    assert detail["code"] == ConflictError.code
    assert detail["details"]["conflicts"][0]["date"] == "2026-11-04"
    # 零污染：外部改动保留、碎片未删
    assert a_path.read_text(encoding="utf-8") == "# 2026-11-04\n\n- 外部新内容\n"
    assert b_path.exists()


def test_apply_second_time_rejected_by_status(prepared):
    client, registry = prepared
    _seed_multi_source_day(registry, "2026-11-05")
    _CURRENT_DATE[0] = "2026-11-05"
    run_id = _create(client, "2026-11-05", "2026-11-05").json()["data"]["run_id"]
    _wait_run(client, run_id)

    assert client.post(f"/api/daily-runs/{run_id}/apply",
                       json={"apply_all": True}).status_code == 200
    again = client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DAILY_RUN_STATUS"


# ---------- 路径穿越 ----------


@pytest.mark.parametrize("bad", ["../etc/passwd", "2026-11-01/../../x", "2026-11-01\\..\\x"])
def test_path_traversal_in_date_is_forbidden(prepared, bad: str):
    client, _ = prepared
    res = _create(client, bad, "2026-11-30")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "UNSAFE_PATH"


def test_invalid_date_is_bad_request(prepared):
    client, _ = prepared
    res = _create(client, "2026-13-45", "2026-11-30")
    assert res.status_code == 400


# ---------- 写前验收：零污染 ----------


def test_write_time_acceptance_blocks_and_writes_nothing(prepared):
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-06")
    _CURRENT_DATE[0] = "2026-11-06"
    # 模型把元数据壳抄回输出：章节合规（生成阶段通过），但写前验收必须拦住
    OUTPUT_OVERRIDE[0] = _doc("2026-11-06", extra="\n- **Session Key**: agent:alpha:main\n")

    run_id = _create(client, "2026-11-06", "2026-11-06").json()["data"]["run_id"]
    run = _wait_run(client, run_id)
    assert run["items"][0]["status"] == drs.ITEM_PLANNED      # 生成阶段放行

    applied = client.post(f"/api/daily-runs/{run_id}/apply",
                          json={"apply_all": True}).json()["data"]
    assert applied["blocked"] == ["2026-11-06"]
    assert applied["applied"] == []
    assert applied["status"] == drs.RUN_NEEDS_REVIEW

    # 零污染：日文件保持原样、碎片未删
    assert a_path.read_text(encoding="utf-8").startswith("# 2026-11-06")
    assert b_path.exists()

    report = client.get(f"/api/daily-runs/{run_id}/report").json()["data"]
    assert report["passed"] is False
    assert report["days_delivered"] == 0
    assert report["items"][0]["details"]            # 给出了原因


# ---------- 碎片删除失败 → partially_applied ----------


def test_fragment_delete_failure_marks_partial(prepared, monkeypatch):
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-07")
    _CURRENT_DATE[0] = "2026-11-07"
    run_id = _create(client, "2026-11-07", "2026-11-07").json()["data"]["run_id"]
    _wait_run(client, run_id)

    def _boom(agent_id: str, path: str) -> None:
        raise OSError("文件被占用")

    monkeypatch.setattr(registry.file_manager, "delete", _boom)
    applied = client.post(f"/api/daily-runs/{run_id}/apply",
                          json={"apply_all": True}).json()["data"]

    assert applied["partial"] == ["2026-11-07"]
    assert applied["status"] == drs.RUN_PARTIAL
    assert a_path.read_text(encoding="utf-8").startswith("# 工作日志 - 2026-11-07")  # 日文件保留不回滚
    assert b_path.exists()                                                          # 碎片还在
    report = client.get(f"/api/daily-runs/{run_id}/report").json()["data"]
    assert report["passed"] is False
    assert report["items"][0]["fragments_gone"] is False


# ---------- 跳过 / 拒绝 / 空范围 / 上限 / 开关 ----------


def test_skip_one_day_then_apply_rest(prepared):
    client, registry = prepared
    _seed_multi_source_day(registry, "2026-11-08")
    _seed_multi_source_day(registry, "2026-11-09")
    _CURRENT_DATE[0] = "2026-11-09"
    run_id = _create(client, "2026-11-08", "2026-11-09").json()["data"]["run_id"]
    _wait_run(client, run_id)

    skipped = client.post(f"/api/daily-runs/{run_id}/skip",
                          json={"dates": ["2026-11-08"]}).json()["data"]
    assert [i["status"] for i in skipped["items"]] == [drs.ITEM_SKIPPED, drs.ITEM_PLANNED]

    applied = client.post(f"/api/daily-runs/{run_id}/apply",
                          json={"dates": ["2026-11-09"]}).json()["data"]
    assert applied["applied"] == ["2026-11-09"]
    assert applied["skipped"] == ["2026-11-08"]
    assert (_root(registry) / "memory/2026-11-08-1415.md").exists()   # 跳过的日子没被动


def test_reject_writes_nothing(prepared):
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-10")
    _CURRENT_DATE[0] = "2026-11-10"
    run_id = _create(client, "2026-11-10", "2026-11-10").json()["data"]["run_id"]
    _wait_run(client, run_id)

    rejected = client.post(f"/api/daily-runs/{run_id}/reject").json()["data"]
    assert rejected["status"] == drs.RUN_REJECTED
    assert a_path.read_text(encoding="utf-8").startswith("# 2026-11-10")
    assert b_path.exists()


def test_range_without_work_is_empty(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-11.md", "# 2026-11-11\n\n- 已精简，无需整理\n")
    res = _create(client, "2026-11-11", "2026-11-11").json()["data"]
    assert res["status"] == drs.RUN_EMPTY
    assert res["days_total"] == 0
    detail = client.get(f"/api/daily-runs/{res['run_id']}").json()["data"]
    assert "没有需要整理的日子" in detail["error"]


def test_max_days_per_run_is_enforced(prepared, monkeypatch):
    client, registry = prepared
    monkeypatch.setattr(registry.config.daily_standardizer, "max_days_per_run", 1)
    _seed_multi_source_day(registry, "2026-11-12")
    _seed_multi_source_day(registry, "2026-11-13")
    res = _create(client, "2026-11-12", "2026-11-13")
    assert res.status_code == 400
    assert "超过单批上限" in res.json()["error"]["message"]


def test_token_budget_stops_batch_and_writes_nothing(prepared, monkeypatch):
    client, registry = prepared
    monkeypatch.setattr(registry.config.daily_standardizer, "token_budget", 200)
    _seed_multi_source_day(registry, "2026-11-14")
    _seed_multi_source_day(registry, "2026-11-15")
    _seed_multi_source_day(registry, "2026-11-16")
    _CURRENT_DATE[0] = "2026-11-16"
    run_id = _create(client, "2026-11-14", "2026-11-16").json()["data"]["run_id"]
    run = _wait_run(client, run_id)

    # 每天 150 tokens：第 1 天 150 未越限，第 2 天后累计 300 > 200 → 中止（不再调 LLM）
    assert len(CALLS) == 2
    assert run["tokens_used"] == 300
    assert "超出单批 token 预算" in run["error"]
    by_date = {i["date"]: i for i in run["items"]}
    assert by_date["2026-11-14"]["status"] == drs.ITEM_PLANNED     # 已生成的计划保留可确认
    assert by_date["2026-11-15"]["status"] == drs.ITEM_PLANNED
    assert by_date["2026-11-16"]["status"] == drs.ITEM_FAILED      # 剩余日期中止
    assert "超出单批 token 预算" in by_date["2026-11-16"]["error"]
    # 未写入任何文件（含已生成的计划——写入必须由人确认）
    for date in ("2026-11-14", "2026-11-15", "2026-11-16"):
        assert (_root(registry) / f"memory/{date}-1415.md").exists()
        assert (_root(registry) / f"memory/{date}.md").read_text(
            encoding="utf-8").startswith(f"# {date}")


def test_dry_run_only_blocks_apply(prepared, monkeypatch):
    client, registry = prepared
    _seed_multi_source_day(registry, "2026-11-16")
    _CURRENT_DATE[0] = "2026-11-16"
    run_id = _create(client, "2026-11-16", "2026-11-16").json()["data"]["run_id"]
    _wait_run(client, run_id)

    monkeypatch.setattr(registry.config.daily_standardizer, "dry_run_only", True)
    res = client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "DAILY_RUN_DISABLED"
    assert (_root(registry) / "memory/2026-11-16-1415.md").exists()


# ---------- 「本日无可归档内容」：模型决策不产出日文件 ----------
# 回归：此前强规则强制必填章节齐全，全天噪音的日子只能硬凑一篇。


def test_empty_day_writes_nothing_and_cleans_fragments(prepared):
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-21")
    _CURRENT_DATE[0] = "2026-11-21"
    OUTPUT_OVERRIDE[0] = "无可归档内容：全天只有巡检心跳，无任何结论"

    run_id = _create(client, "2026-11-21", "2026-11-21").json()["data"]["run_id"]
    run = _wait_run(client, run_id)

    # 有碎片要清 → 仍需人工确认
    assert run["status"] == drs.RUN_AWAITING
    item = run["items"][0]
    assert item["status"] == drs.ITEM_EMPTY
    assert item["empty_reason"] == "全天只有巡检心跳，无任何结论"
    assert not item["output_content"]                 # 没有产出内容（更不会硬凑）
    assert item["html_diff"] is None
    assert item["fragments_to_delete"] == ["memory/2026-11-21-1415.md"]  # 只含 B/C
    # 未确认前磁盘一个字节都没动
    assert a_path.read_text(encoding="utf-8").startswith("# 2026-11-21")
    assert b_path.exists()

    res = client.post(f"/api/daily-runs/{run_id}/apply",
                      json={"apply_all": True}).json()["data"]
    assert res["no_content"] == ["2026-11-21"]
    assert res["applied"] == []
    assert res["status"] == drs.RUN_EMPTY

    # 主文件原样保留（未改写、未删除），碎片已清理
    assert a_path.read_text(encoding="utf-8") == "# 2026-11-21\n\n- 主骨架事实：日常巡检完成\n"
    assert not b_path.exists()

    report = client.get(f"/api/daily-runs/{run_id}/report").json()["data"]
    assert report["passed"] is True
    assert report["days_delivered"] == 0
    entry = report["items"][0]
    assert entry["empty"] is True
    assert entry["fragments_gone"] is True
    assert "无可归档内容" in "；".join(entry["details"])


def test_empty_day_without_fragments_needs_no_confirmation(prepared):
    """只有主文件的空日：没有要清理的碎片 → 批次直接落到 empty，不需要「执行」。"""
    client, registry = prepared
    # 单来源但要整理（心跳刷屏，判为低质量）→ 该日会进批次，且没有 B/C 碎片可清
    a_path = _write(registry, "memory/2026-11-22.md",
                    f"# 2026-11-22\n\n{chr(10).join('- HEARTBEAT_OK' for _ in range(25))}\n")
    _CURRENT_DATE[0] = "2026-11-22"
    OUTPUT_OVERRIDE[0] = "无可归档内容：只有心跳"

    run_id = _create(client, "2026-11-22", "2026-11-22").json()["data"]["run_id"]
    run = _wait_run(client, run_id)

    assert run["status"] == drs.RUN_EMPTY
    assert run["items"][0]["status"] == drs.ITEM_EMPTY
    assert run["items"][0]["fragments_to_delete"] == []
    assert a_path.read_text(encoding="utf-8").startswith("# 2026-11-22")  # 主文件未被改写


def test_mixed_batch_writes_only_the_day_with_content(prepared):
    client, registry = prepared
    keep_a, keep_b = _seed_multi_source_day(registry, "2026-11-23")
    empty_a, empty_b = _seed_multi_source_day(registry, "2026-11-24")
    _CURRENT_DATE[0] = "2026-11-23"
    OUTPUT_OVERRIDE_BY_DAY["2026-11-24"] = "无可归档内容：只有心跳与端口轮询"

    run_id = _create(client, "2026-11-23", "2026-11-24").json()["data"]["run_id"]
    run = _wait_run(client, run_id)
    by_date = {i["date"]: i for i in run["items"]}
    assert by_date["2026-11-23"]["status"] == drs.ITEM_PLANNED
    assert by_date["2026-11-24"]["status"] == drs.ITEM_EMPTY

    res = client.post(f"/api/daily-runs/{run_id}/apply",
                      json={"apply_all": True}).json()["data"]
    assert res["applied"] == ["2026-11-23"]
    assert res["no_content"] == ["2026-11-24"]
    assert res["status"] == drs.RUN_APPLIED

    assert keep_a.read_text(encoding="utf-8").startswith("# 工作日志 - 2026-11-23")
    assert not keep_b.exists()
    # 空日：不写新内容、主文件保持原样，碎片照常清理
    assert empty_a.read_text(encoding="utf-8").startswith("# 2026-11-24")
    assert not empty_b.exists()


def test_empty_day_fragment_changed_after_plan_blocks_batch(prepared):
    """空日清碎片前照样过乐观锁：碎片被外部改动 → 整批不写、不删。"""
    client, registry = prepared
    a_path, b_path = _seed_multi_source_day(registry, "2026-11-25")
    _CURRENT_DATE[0] = "2026-11-25"
    OUTPUT_OVERRIDE[0] = "无可归档内容：只有心跳"
    run_id = _create(client, "2026-11-25", "2026-11-25").json()["data"]["run_id"]
    _wait_run(client, run_id)

    b_path.write_text("HEARTBEAT_OK\n", encoding="utf-8")  # 计划后被外部改动

    res = client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})
    assert res.status_code == 409
    assert b_path.exists()                                                # 没删
    assert a_path.read_text(encoding="utf-8").startswith("# 2026-11-25")  # 一个字没动
