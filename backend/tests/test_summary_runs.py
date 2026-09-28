"""集成测试：工作日志总结（记忆归纳）批次（M16）。

覆盖：正常流程（创建 → 生成计划 → 确认写入 → 验收）/ 产物命名（整月 vs 跨段）/
空范围 / 幂等复用 / 乐观锁 409 / 拒绝 / 可选清理源文件 / 全局 dry-run 开关 /
跨度上限 / 日期路径穿越。LLM 全部 mock；**每一步都核对磁盘真实状态**。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.services import summary_service as ss
from app.services.llm_registry import LLMResponse, LLMTokenUsage

PROVIDER = {
    "id": "summary-test-provider",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-test-000",
    "model": "gpt-4o",
    "protocol": "openai-completions",
}
PRESET_ID = "preset-mem-summarize"

CALLS: list[list[dict]] = []
OUTPUT_OVERRIDE: list[str | None] = [None]


def _doc(span: str) -> str:
    return (
        f"# {span} 记忆归纳\n\n"
        "> 生成时间：2026-09-26\n\n"
        "## 一、完成的工作\n\n"
        "- **端口仪表盘**：刷新完成\n\n"
        "## 二、经验教训\n\n"
        "| 日期 | 教训 |\n"
        "|------|------|\n"
        "| 11-01 | **不知道就说不知道，不准编造** |\n\n"
        "## 三、重要决定\n\n"
        "| 日期 | 决定 |\n"
        "|------|------|\n"
        "| 11-01 | 默认模型切换 |\n\n"
        "## 四、重要信息\n\n"
        "- 用户：阮晨华，律师\n\n"
        "## 五、待办事项\n\n"
        "- [ ] 复核 8420 GC 后水位\n"
    )


async def _fake_chat(self, messages, max_tokens=None, temperature=None):
    CALLS.append(messages)
    return LLMResponse(
        content=OUTPUT_OVERRIDE[0] if OUTPUT_OVERRIDE[0] is not None else _doc("2026-11"),
        usage=LLMTokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate_usd=0.0025,
    )


@pytest.fixture()
def prepared(client, registry, monkeypatch):
    client.post("/api/llm/providers", json=PROVIDER)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat)
    CALLS.clear()
    OUTPUT_OVERRIDE[0] = None
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
    return client.post("/api/summary-runs", json=body)


def _wait_run(client, run_id: str, timeout: float = 5.0) -> dict:
    """等后台归纳结束（planned → awaiting_confirm / failed / empty）。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/summary-runs/{run_id}").json()["data"]
        if last["status"] != ss.RUN_PLANNED:
            return last
        time.sleep(0.05)
    raise AssertionError(f"批次 {run_id} 未在 {timeout}s 内结束：{last and last['status']}")


# ---------- 正常流程 ----------


def test_full_flow_plan_confirm_then_report(prepared):
    client, registry = prepared
    a = _write(registry, "memory/2026-11-01.md", "# 2026-11-01\n\n- 巡检完成\n")
    b = _write(registry, "memory/2026-11-01-1415.md",
               "# Session: 2026-11-01 14:15:00 Asia/Shanghai\n\n"
               "- **Session Key**: agent:alpha:main\n\n"
               "assistant: \"端口仪表盘已刷新。\"\n")

    created = _create(client, "2026-11-01", "2026-11-30").json()["data"]
    assert created["status"] == ss.RUN_PLANNED
    assert created["source_count"] == 2
    assert created["reused"] is False

    run = _wait_run(client, created["run_id"])
    assert run["status"] == ss.RUN_AWAITING
    # 整月 → 产物命名为 YYYY-MM
    assert run["output_path"] == "memory/2026-11-记忆归纳.md"
    assert run["sources"][0]["path"] == "memory/2026-11-01.md"
    assert run["format_report"]["ok"] is True
    assert run["html_diff"] and "<" in run["html_diff"]
    assert run["tokens_used"] == 150

    # 未确认前：一个字节都没动
    assert a.read_text(encoding="utf-8").startswith("# 2026-11-01")
    assert b.exists()
    assert not (_root(registry) / "memory/2026-11-记忆归纳.md").exists()

    applied = client.post(f"/api/summary-runs/{created['run_id']}/apply").json()["data"]
    assert applied["status"] == ss.RUN_APPLIED
    assert applied["backup_id"] is None      # 目标文件是新建，无备份

    # 汇总文件已写入；**源文件默认不动**
    out = (_root(registry) / "memory/2026-11-记忆归纳.md").read_text(encoding="utf-8")
    assert out.startswith("# 2026-11 记忆归纳")
    assert "## 五、待办事项" in out
    assert a.exists() and b.exists()

    report = client.get(f"/api/summary-runs/{created['run_id']}/report").json()["data"]
    assert report["passed"] is True
    assert report["delivered"] and report["naming_ok"]
    assert report["sections_ok"] and report["no_residue"] and report["sources_ok"]


def test_partial_range_uses_from_to_naming(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-12-02.md", "# 2026-12-02\n\n- 事项\n")
    run_id = _create(client, "2026-12-01", "2026-12-03").json()["data"]["run_id"]
    run = _wait_run(client, run_id)
    assert run["output_path"] == "memory/2026-12-01_2026-12-03-记忆归纳.md"


def test_apply_writes_backup_and_audit(prepared):
    client, registry = prepared
    output = _write(registry, "memory/2026-11-记忆归纳.md", "# 2026-11 记忆归纳\n\n旧内容\n")
    _write(registry, "memory/2026-11-05.md", "# 2026-11-05\n\n- 事项\n")

    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)
    client.post(f"/api/summary-runs/{run_id}/apply")

    detail = client.get(f"/api/summary-runs/{run_id}").json()["data"]
    assert detail["backup_id"]                       # 覆盖既有文件 → 写前自动备份
    assert output.read_text(encoding="utf-8").startswith("# 2026-11 记忆归纳")
    actions = [a["action"] for a in client.get("/api/audit", params={"limit": 50}).json()["data"]]
    assert "summary_run_create" in actions and "summary_apply" in actions


# ---------- 空范围 / 幂等 ----------


def test_empty_range_returns_empty_status(prepared):
    client, _registry = prepared
    created = _create(client, "2020-01-01", "2020-01-31").json()["data"]
    assert created["status"] == ss.RUN_EMPTY
    assert created["source_count"] == 0
    assert len(CALLS) == 0                            # 空范围不调 LLM
    run = client.get(f"/api/summary-runs/{created['run_id']}").json()["data"]
    assert run["error"]
    assert client.post(f"/api/summary-runs/{created['run_id']}/apply").status_code == 409


def test_same_scope_same_content_reuses_run(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-03.md", "# 2026-11-03\n\n- 事项\n")

    first = _create(client, "2026-11-01", "2026-11-30").json()["data"]
    _wait_run(client, first["run_id"])
    calls_after_first = len(CALLS)

    second = _create(client, "2026-11-01", "2026-11-30").json()["data"]
    assert second["reused"] is True
    assert second["run_id"] == first["run_id"]
    assert len(CALLS) == calls_after_first            # 没有第二次 LLM 调用


# ---------- 乐观锁 / 状态机 ----------


def test_apply_conflicts_when_target_changed_after_plan(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-04.md", "# 2026-11-04\n\n- 事项\n")
    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)

    # 计划生成后目标文件被外部创建（等价于「另一个批次抢先确认」）
    _write(registry, "memory/2026-11-记忆归纳.md", "# 2026-11 记忆归纳\n\n外部抢先写入\n")

    res = client.post(f"/api/summary-runs/{run_id}/apply")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"
    # 零污染：外部内容保留
    assert "外部抢先写入" in (_root(registry) / "memory/2026-11-记忆归纳.md").read_text(encoding="utf-8")


def test_reject_writes_nothing(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-06.md", "# 2026-11-06\n\n- 事项\n")
    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)

    rejected = client.post(f"/api/summary-runs/{run_id}/reject").json()["data"]
    assert rejected["status"] == ss.RUN_REJECTED
    assert not (_root(registry) / "memory/2026-11-记忆归纳.md").exists()
    # 终态不可再写入
    assert client.post(f"/api/summary-runs/{run_id}/apply").status_code == 409


def test_apply_second_time_rejected_by_status(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-07.md", "# 2026-11-07\n\n- 事项\n")
    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)
    assert client.post(f"/api/summary-runs/{run_id}/apply").status_code == 200
    assert client.post(f"/api/summary-runs/{run_id}/apply").status_code == 409


# ---------- 可选：清理源文件 ----------


def test_cleanup_sources_after_apply_moves_files_to_trash(prepared):
    client, registry = prepared
    a = _write(registry, "memory/2026-11-08.md", "# 2026-11-08\n\n- 事项\n")
    b = _write(registry, "memory/2026-11-08-1415.md", "# Session: x\n\n- 明细\n")
    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)
    assert client.post(f"/api/summary-runs/{run_id}/apply").json()["data"]["applied_at"]

    res = client.post(f"/api/summary-runs/{run_id}/cleanup-sources").json()["data"]
    assert res["deleted"] == ["memory/2026-11-08.md", "memory/2026-11-08-1415.md"]
    assert res["failed"] == []
    assert not a.exists() and not b.exists()
    # 产物自身永不删除
    assert (_root(registry) / "memory/2026-11-记忆归纳.md").exists()

    report = client.get(f"/api/summary-runs/{run_id}/report").json()["data"]
    assert report["sources_ok"] is True
    # 重复清理 → 409
    assert client.post(f"/api/summary-runs/{run_id}/cleanup-sources").status_code == 409


def test_cleanup_requires_applied_run(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-09.md", "# 2026-11-09\n\n- 事项\n")
    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)
    res = client.post(f"/api/summary-runs/{run_id}/cleanup-sources")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "SUMMARY_RUN_STATUS"


# ---------- 护栏 ----------


def test_dry_run_only_blocks_apply(prepared):
    client, registry = prepared
    _write(registry, "memory/2026-11-10.md", "# 2026-11-10\n\n- 事项\n")
    run_id = _create(client, "2026-11-01", "2026-11-30").json()["data"]["run_id"]
    _wait_run(client, run_id)

    registry.config.summarizer.dry_run_only = True
    res = client.post(f"/api/summary-runs/{run_id}/apply")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SUMMARY_RUN_DISABLED"


def test_range_over_limit_rejected(prepared):
    client, _registry = prepared
    res = _create(client, "2026-01-01", "2026-04-30")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


def test_date_path_traversal_rejected(prepared):
    client, _registry = prepared
    res = _create(client, "2026-11-01/../x", "2026-11-30")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "UNSAFE_PATH"
