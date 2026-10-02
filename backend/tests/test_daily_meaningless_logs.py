"""集成测试：大模型「无意义日志自动删除」开关（M15 扩展）。

覆盖需求：
1. 配置开关生效（API 往返 + 执行流程判断）
2. 仅开关开启时才触发大模型筛选与删除流程；关闭时零额外调用、零归档
3. 被判定为无意义并删除的日志，删除前必有 7 天备份归档（磁盘真实核对）
4. 备份失败时不删除（保守）
LLM 全部 mock；每一步都核对磁盘真实状态。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from app.services import daily_run_service as drs
from app.services.llm_registry import LLMResponse, LLMTokenUsage

PROVIDER = {
    "id": "mlog-test-provider",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-test-000",
    "model": "gpt-4o",
    "protocol": "openai-completions",
}
PRESET_ID = "preset-wlog-daily-std"

SCREEN_CALLS: list[list[dict]] = []
MERGE_CALLS: list[list[dict]] = []
SCREEN_RESPONSES: list[str] = []
_CURRENT_DATE: list[str] = [""]
_PROMPT_DATE_RE = re.compile(r"【任务】把 (\d{4}-\d{2}-\d{2}) 这一天")


def _doc(date: str) -> str:
    return (
        f"# 工作日志 - {date}\n\n"
        "## 一、今日概览\n\n"
        "- **日期**：" + date + "\n"
        "- **核心活动**：端口仪表盘刷新完成\n\n"
        "## 二、关键事件\n\n"
        "### 事件 1\n\n"
        "- 事实：22 个端口、RSS 总 2832 MB\n\n"
        "## 三、关键决策\n\n"
        "| 决策项 | 内容 |\n"
        "|--------|------|\n"
        "| 8420 水位 | 纳入观察 |\n\n"
        "## 四、待办事项\n\n"
        "- [ ] 复核 8420 GC 后水位\n\n"
        "## 五、明日计划\n\n"
        "- 观察 8420 GC 后水位\n"
    )


async def _router_chat(self, messages, max_tokens=None, temperature=None):
    user = messages[-1]["content"]
    if "无意义日志的判定维度" in user:          # 命中筛选 prompt
        SCREEN_CALLS.append(messages)
        content = SCREEN_RESPONSES.pop(0) if SCREEN_RESPONSES else '{"meaningless": []}'
        return LLMResponse(
            content=content,
            usage=LLMTokenUsage(prompt_tokens=40, completion_tokens=20, total_tokens=60),
            cost_estimate_usd=0.001,
        )
    MERGE_CALLS.append(messages)
    match = _PROMPT_DATE_RE.search(user)
    date = match.group(1) if match else _CURRENT_DATE[0]
    return LLMResponse(
        content=_doc(date),
        usage=LLMTokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate_usd=0.0025,
    )


@pytest.fixture()
def prepared(client, registry, monkeypatch):
    client.post("/api/llm/providers", json=PROVIDER)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _router_chat)
    SCREEN_CALLS.clear()
    MERGE_CALLS.clear()
    SCREEN_RESPONSES.clear()
    SCREEN_RESPONSES.append('{"meaningless": []}')   # 默认：无无意义日志
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
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/daily-runs/{run_id}").json()["data"]
        if last["status"] != drs.RUN_PLANNED:
            return last
        time.sleep(0.05)
    raise AssertionError(f"批次 {run_id} 未在 {timeout}s 内结束：{last and last['status']}")


def _seed_multi_source_day(registry, date: str) -> tuple[Path, Path]:
    a = _write(registry, f"memory/{date}.md", f"# {date}\n\n- 主骨架事实：日常巡检完成\n")
    b = _write(registry, f"memory/{date}-1415.md", (
        "# Session: " + date + " 14:15:00 Asia/Shanghai\n\n"
        "- **Session Key**: agent:alpha:main\n\n"
        "HEARTBEAT_OK\n\n"
        "assistant: \"端口轮询中…\"\n"))
    return a, b


def _set_switch(registry, enabled: bool) -> None:
    registry.config.daily_standardizer.auto_delete_meaningless_logs = enabled


# ---------- 开关关闭：保持既有行为 ----------


def test_switch_off_keeps_existing_behavior(prepared):
    client, registry = prepared
    _set_switch(registry, False)
    _, b_path = _seed_multi_source_day(registry, "2026-12-01")
    _CURRENT_DATE[0] = "2026-12-01"

    run_id = _create(client, "2026-12-01", "2026-12-01").json()["data"]["run_id"]
    run = _wait_run(client, run_id)

    assert SCREEN_CALLS == []                       # 关闭时不触发大模型筛选
    assert len(MERGE_CALLS) == 1
    assert run["items"][0]["meaningless_logs"] == []
    assert run["tokens_used"] == 150                # 只有归并调用

    client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})
    assert not b_path.exists()                      # 碎片照常删除（既有行为）
    assert registry.meaningless_archive.entries() == []   # 不产生归档


# ---------- 开关开启：筛选 + 删除前备份 ----------


def test_switch_on_screens_archives_then_deletes(prepared):
    client, registry = prepared
    _set_switch(registry, True)
    _, b_path = _seed_multi_source_day(registry, "2026-12-02")
    _CURRENT_DATE[0] = "2026-12-02"
    SCREEN_RESPONSES[0] = json.dumps({"meaningless": [
        {"path": "memory/2026-12-02-1415.md", "dimension": "debug_noise",
         "reason": "只有心跳与端口轮询，无结论"},
    ]}, ensure_ascii=False)
    original = b_path.read_text(encoding="utf-8")

    run_id = _create(client, "2026-12-02", "2026-12-02").json()["data"]["run_id"]
    run = _wait_run(client, run_id)

    assert len(SCREEN_CALLS) == 1                   # 开启时触发筛选
    assert run["tokens_used"] == 210                # 归并 150 + 筛选 60，均计入预算
    findings = run["items"][0]["meaningless_logs"]
    assert len(findings) == 1
    assert findings[0]["dimension"] == "debug_noise"
    assert findings[0]["dimension_name"] == "无业务价值的调试信息"
    assert findings[0]["backup_path"] is None        # 计划阶段还没备份（只读）

    # 未确认前：磁盘未动、无归档
    assert b_path.exists()
    assert registry.meaningless_archive.entries() == []

    applied = client.post(f"/api/daily-runs/{run_id}/apply",
                          json={"apply_all": True}).json()["data"]
    assert applied["applied"] == ["2026-12-02"]
    assert not b_path.exists()                       # 删除

    entries = registry.meaningless_archive.entries()
    assert len(entries) == 1                         # 删除前已备份
    assert entries[0].path == "memory/2026-12-02-1415.md"
    assert Path(entries[0].backup_path).read_text(encoding="utf-8") == original

    # 备份路径回填到条目，可供 7 天可追溯
    detail = client.get(f"/api/daily-runs/{run_id}").json()["data"]
    assert detail["items"][0]["meaningless_logs"][0]["backup_path"] == entries[0].backup_path
    assert detail["items"][0]["meaningless_logs"][0]["archived_at"]

    actions = [a["action"] for a in client.get("/api/audit", params={"limit": 50}).json()["data"]]
    assert "daily_apply" in actions


def test_switch_on_empty_verdict_deletes_without_archive(prepared):
    client, registry = prepared
    _set_switch(registry, True)
    _, b_path = _seed_multi_source_day(registry, "2026-12-03")
    _CURRENT_DATE[0] = "2026-12-03"
    SCREEN_RESPONSES[0] = '{"meaningless": []}'     # 模型认为碎片都有价值

    run_id = _create(client, "2026-12-03", "2026-12-03").json()["data"]["run_id"]
    run = _wait_run(client, run_id)
    assert len(SCREEN_CALLS) == 1
    assert run["items"][0]["meaningless_logs"] == []

    client.post(f"/api/daily-runs/{run_id}/apply", json={"apply_all": True})
    assert not b_path.exists()                      # 碎片仍按既有流程删除
    assert registry.meaningless_archive.entries() == []   # 无「无意义」判定 → 不归档


def test_switch_on_but_no_fragments_makes_no_screen_call(prepared):
    """只有单个低质量 A 主文件（无碎片）时，没有可判定的候选 → 不发起筛选调用。"""
    client, registry = prepared
    _set_switch(registry, True)
    _write(registry, "memory/2026-12-04.md",
           f"# 2026-12-04\n\n{chr(10).join('- HEARTBEAT_OK' for _ in range(25))}\n")
    _CURRENT_DATE[0] = "2026-12-04"

    run_id = _create(client, "2026-12-04", "2026-12-04").json()["data"]["run_id"]
    run = _wait_run(client, run_id)
    assert SCREEN_CALLS == []
    assert run["tokens_used"] == 150


# ---------- 备份失败 → 不删除（保守） ----------


def test_backup_failure_skips_deletion(prepared, monkeypatch):
    client, registry = prepared
    _set_switch(registry, True)
    _, b_path = _seed_multi_source_day(registry, "2026-12-05")
    _CURRENT_DATE[0] = "2026-12-05"
    SCREEN_RESPONSES[0] = json.dumps({"meaningless": [
        {"path": "memory/2026-12-05-1415.md", "dimension": "empty_content", "reason": "空"},
    ]}, ensure_ascii=False)

    run_id = _create(client, "2026-12-05", "2026-12-05").json()["data"]["run_id"]
    _wait_run(client, run_id)

    def _boom(*args, **kwargs):
        raise OSError("归档目录不可写")

    monkeypatch.setattr(registry.meaningless_archive, "archive", _boom)
    applied = client.post(f"/api/daily-runs/{run_id}/apply",
                          json={"apply_all": True}).json()["data"]

    assert applied["partial"] == ["2026-12-05"]      # 备份失败 → 该日部分成功
    assert b_path.exists()                           # 未删除（宁可留文件）


# ---------- 配置开关 API 往返 ----------


def test_config_api_toggles_switch(client, registry):
    default = client.get("/api/config").json()["data"]["daily_standardizer"]
    assert default["auto_delete_meaningless_logs"] is False   # 默认关闭

    res = client.put("/api/config", json={
        "daily_standardizer": {"auto_delete_meaningless_logs": True}})
    assert res.status_code == 200
    assert res.json()["data"]["daily_standardizer"]["auto_delete_meaningless_logs"] is True
    assert registry.config.daily_standardizer.auto_delete_meaningless_logs is True

    # 落盘后可被重新读取（config.toml）
    raw = (registry.config.data_dir / "config.toml").read_text(encoding="utf-8")
    assert "auto_delete_meaningless_logs = true" in raw
