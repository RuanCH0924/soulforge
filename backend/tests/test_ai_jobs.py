"""集成测试：AI 自动整理（M13 · Phase 2.5 Step 3）。

LLM 调用通过 mock 避免真实网络；后台任务用轮询等待结束。
覆盖：状态机流转 / 30KB 拦截 / lint 拦截 / 应用写备份 / 拒绝 / 重新生成。
"""
from __future__ import annotations

import time

from app.services.llm_registry import LLMResponse, LLMTokenUsage

PROVIDER = {
    "id": "ai-test-provider",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-test-000",
    "model": "gpt-4o",
    "protocol": "openai-completions",
}

GOOD_OUTPUT = (
    "# 整理后\n\n"
    "## 核心行为准则\n\n简洁、目标导向。\n\n"
    "## 工作态度和原则\n\n先想后做。\n\n"
    "## 学习与连续性\n\n记录与演进。\n\n"
    "## 核心边界\n\n隐私与授权。\n"
)

# 格式合规（含全部必填章节），但触发 lint「最后修订」规则
LINT_BAD_OUTPUT = (
    "# 整理后\n\n"
    "## 核心行为准则\n\n简洁。\n\n"
    "## 工作态度和原则\n\n先想后做。\n\n"
    "## 学习与连续性\n\n记录。\n\n"
    "## 核心边界\n\n隐私。\n\n"
    "最后修订：2026-01-01\n"
)

# 格式违规：缺失必填章节、缺章节标题后空行、含 emoji、用 * 列表
FORMAT_BAD_OUTPUT = (
    "# 整理后\n\n"
    "## 工作态度和原则\n"
    "* 先想后做\n\n"
    "## 学习与连续性\n\n记录。\n\n"
    "## 核心边界\n\n隐私。\n\n"
    "遗留内容。\n"
)

# 格式违规 → 可被 auto_fix 机械修正：Setext 下划线 + emoji 标题 + 混合列表前缀
FIXABLE_BAD_OUTPUT = (
    "# 整理后\n"
    "核心行为准则\n"
    "--------\n"
    "## 工作态度和原则 🚀\n"
    "* 先想后做\n\n"
    "## 学习与连续性\n\n记录。\n\n"
    "## 核心边界\n\n隐私。\n"
)


def _setup(client):
    client.post("/api/llm/providers", json=PROVIDER)


def _wait_job(client, job_id: str, timeout: float = 4.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        res = client.get(f"/api/ai/jobs/{job_id}")
        last = res.json()["data"]
        if last["status"] in ("awaiting_confirm", "failed", "applied"):
            return last
        time.sleep(0.05)
    raise AssertionError(
        f"job {job_id} 未在 {timeout}s 内结束：{last['status'] if last else '无响应'} "
        f"error={last.get('error') if last else None}")


async def _fake_chat_good(self, messages, max_tokens=None, temperature=None):
    return LLMResponse(
        content=GOOD_OUTPUT,
        usage=LLMTokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate_usd=0.0025,
    )


async def _fake_chat_bad(self, messages, max_tokens=None, temperature=None):
    return LLMResponse(
        content=LINT_BAD_OUTPUT,
        usage=LLMTokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost_estimate_usd=0.0001,
    )


async def _fake_chat_format_bad(self, messages, max_tokens=None, temperature=None):
    return LLMResponse(
        content=FORMAT_BAD_OUTPUT,
        usage=LLMTokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost_estimate_usd=0.0001,
    )


async def _fake_chat_fixable_bad(self, messages, max_tokens=None, temperature=None):
    return LLMResponse(
        content=FIXABLE_BAD_OUTPUT,
        usage=LLMTokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost_estimate_usd=0.0001,
    )


def _create_job(client):
    res = client.post("/api/ai/jobs", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
        "preset_id": "preset-soul-std", "provider_id": PROVIDER["id"],
    })
    assert res.status_code == 202
    return res.json()["data"]["job_id"]


# ---------- 异步执行 / 状态机 ----------

def test_create_and_await_confirm(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_good)
    job_id = _create_job(client)

    job = _wait_job(client, job_id)
    assert job["status"] == "awaiting_confirm"
    assert job["input_snapshot"]
    assert job["output_content"] == GOOD_OUTPUT.strip()
    assert job["diff_plan_json"]["unified_diff"]
    assert job["diff_plan_json"]["lint_warnings"] == []
    assert job["total_tokens"] == 150
    assert job["cost_estimate_usd"] == 0.0025


def test_apply_writes_with_backup_and_audit(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_good)
    job_id = _create_job(client)
    _wait_job(client, job_id)

    res = client.post(f"/api/ai/jobs/{job_id}/apply")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "applied"
    assert data["backup_id"] is not None

    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "## 核心行为准则" in content

    audit = client.get("/api/audit").json()["data"]
    assert any(a["action"] == "ai_apply" for a in audit)


def test_apply_wrong_status_conflict(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_good)
    job_id = _create_job(client)
    _wait_job(client, job_id)

    assert client.post(f"/api/ai/jobs/{job_id}/apply").status_code == 200
    res = client.post(f"/api/ai/jobs/{job_id}/apply")  # 已 applied，再应用 → 409
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AI_JOB_STATUS"


def test_reject_keeps_file(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_good)
    before = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    job_id = _create_job(client)
    _wait_job(client, job_id)

    res = client.post(f"/api/ai/jobs/{job_id}/reject")
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "rejected"
    after = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert after == before


# ---------- 安全护栏 ----------

def test_apply_lint_blocked_422(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_bad)
    job_id = _create_job(client)
    job = _wait_job(client, job_id)
    # 输出格式合规但含「最后修订」→ 执行时已记录 lint 警告，状态仍为 awaiting_confirm
    assert job["diff_plan_json"]["format_report"]["ok"] is True
    assert job["diff_plan_json"]["lint_warnings"]

    res = client.post(f"/api/ai/jobs/{job_id}/apply")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "AI_LINT_BLOCKED"
    # 状态流转为 failed
    assert client.get(f"/api/ai/jobs/{job_id}").json()["data"]["status"] == "failed"
    # 文件未被写入
    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "最后修订" not in content


def test_apply_format_violation_blocked_422(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_format_bad)
    job_id = _create_job(client)
    job = _wait_job(client, job_id)
    # 输出缺少必填章节「核心行为准则」→ 机械修正无法补齐 → format_report.not ok
    assert job["diff_plan_json"]["format_report"]["ok"] is False
    rule_ids = {v["rule_id"] for v in job["diff_plan_json"]["format_report"]["violations"]}
    assert "STR-MISSING-SECTION" in rule_ids

    res = client.post(f"/api/ai/jobs/{job_id}/apply")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "FORMAT_VIOLATION"
    assert client.get(f"/api/ai/jobs/{job_id}").json()["data"]["status"] == "failed"
    # 文件未被写入（保持原内容）
    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "## 工作态度和原则" not in content


def test_auto_fix_produces_compliant_output(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_fixable_bad)
    job_id = _create_job(client)
    job = _wait_job(client, job_id)
    # 机械修正后 100% 合规：format_report.ok 且章节齐全
    assert job["diff_plan_json"]["format_report"]["ok"] is True
    output = job["output_content"]
    assert "## 核心行为准则" in output       # Setext 下划线 → ATX 标题
    assert "## 工作态度和原则" in output     # 标题 emoji 已剔除
    assert "* 先想后做" not in output
    assert "- 先想后做" in output             # 列表前缀统一为「- 」

    res = client.post(f"/api/ai/jobs/{job_id}/apply")
    assert res.status_code == 200
    content = client.get("/api/agents/alpha/files/SOUL.md").json()["data"]["content"]
    assert "## 核心行为准则" in content


def test_large_file_rejected(client):
    _setup(client)
    big = "# 大文件\n\n" + "x" * (31 * 1024)
    client.put("/api/agents/alpha/files/notes/big.md", json={"content": big})
    res = client.post("/api/ai/jobs", json={
        "agent_id": "alpha", "file_path": "notes/big.md",
        "preset_id": "preset-soul-std", "provider_id": PROVIDER["id"],
    })
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "AI_FILE_TOO_LARGE"


def test_create_job_missing_file(client):
    _setup(client)
    res = client.post("/api/ai/jobs", json={
        "agent_id": "alpha", "file_path": "notes/nope.md",
        "preset_id": "preset-soul-std", "provider_id": PROVIDER["id"],
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_create_job_unknown_provider(client):
    res = client.post("/api/ai/jobs", json={
        "agent_id": "alpha", "file_path": "SOUL.md",
        "preset_id": "preset-soul-std", "provider_id": "ghost",
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "LLM_PROVIDER_NOT_FOUND"


# ---------- 重新生成 ----------

def test_regenerate_supersedes_old_job(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_good)
    job_id = _create_job(client)
    _wait_job(client, job_id)

    res = client.post(f"/api/ai/jobs/{job_id}/regenerate", json={"extra_instructions": "补上「核心边界」"})
    assert res.status_code == 202
    new_id = res.json()["data"]["job_id"]
    assert new_id != job_id

    old = client.get(f"/api/ai/jobs/{job_id}").json()["data"]
    assert old["status"] == "superseded"
    assert old["superseded_by"] == new_id

    new = _wait_job(client, new_id)
    assert new["status"] == "awaiting_confirm"
    assert new["extra_instructions"] == "补上「核心边界」"


# ---------- 列表 ----------

def test_list_jobs(client, monkeypatch):
    _setup(client)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_good)
    job_id = _create_job(client)
    _wait_job(client, job_id)

    res = client.get("/api/ai/jobs", params={"agent_id": "alpha", "limit": 50})
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == job_id
    assert data[0]["status"] == "awaiting_confirm"


def test_get_job_not_found(client):
    res = client.get("/api/ai/jobs/ghost")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "AI_JOB_NOT_FOUND"
