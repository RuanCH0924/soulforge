"""集成测试：LLM Provider 接入（M12 · Phase 2.5 Step 2）。

覆盖：CRUD / 密钥加密存储与掩码 / PUT 保留旧 key / 热加载 / 测试连通性（mock）/ 删除保护。
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.core.errors import LLMOutputTruncatedError
from app.models.db import LLMProviderRow
from app.services.llm_registry import LLMClient, LLMProvider, LLMResponse, LLMTokenUsage

PAYLOAD = {
    "id": "openai-test",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-secret-1234567890",
    "model": "gpt-4o",
    "protocol": "openai-completions",
    "max_tokens": 4096,
    "temperature": 0.3,
    "timeout_seconds": 60,
}


# ---------- CRUD + 加密 ----------

def test_create_provider_encrypts_key(client, registry):
    res = client.post("/api/llm/providers", json=PAYLOAD)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["id"] == "openai-test"
    assert data["enabled"] is True
    # 掩码：不含明文
    assert "sk-secret" not in data["api_key_masked"]
    assert "****" in data["api_key_masked"]

    # DB 里存的是密文，解密后与明文一致
    with registry.db.session() as s:
        row = s.get(LLMProviderRow, "openai-test")
        assert row.api_key_encrypted != PAYLOAD["api_key"]
        assert registry.key_vault.decrypt(row.api_key_encrypted) == PAYLOAD["api_key"]

    # 热加载：内存注册表里已可用
    assert registry.llm.get_provider("openai-test").base_url == PAYLOAD["base_url"]


def test_list_providers(client):
    client.post("/api/llm/providers", json=PAYLOAD)
    res = client.get("/api/llm/providers")
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == "openai-test"
    assert data[0]["api_key_masked"] != PAYLOAD["api_key"]


def test_create_provider_invalid_protocol(client):
    body = {**PAYLOAD, "protocol": "grpc"}
    res = client.post("/api/llm/providers", json=body)
    assert res.status_code == 422


def test_create_provider_missing_key(client):
    body = {k: v for k, v in PAYLOAD.items() if k != "api_key"}
    res = client.post("/api/llm/providers", json=body)
    assert res.status_code == 422


# ---------- 更新 / 保留旧 key ----------

def test_update_provider_keep_key(client, registry):
    client.post("/api/llm/providers", json=PAYLOAD)
    res = client.put("/api/llm/providers/openai-test", json={"model": "gpt-4o-mini"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["model"] == "gpt-4o-mini"
    # key 未传 → 保留旧 key
    with registry.db.session() as s:
        row = s.get(LLMProviderRow, "openai-test")
        assert registry.key_vault.decrypt(row.api_key_encrypted) == PAYLOAD["api_key"]
    # 热加载生效
    assert registry.llm.get_provider("openai-test").model == "gpt-4o-mini"


def test_update_provider_change_key(client, registry):
    client.post("/api/llm/providers", json=PAYLOAD)
    client.put("/api/llm/providers/openai-test", json={"api_key": "sk-new-key-000"})
    with registry.db.session() as s:
        row = s.get(LLMProviderRow, "openai-test")
        assert registry.key_vault.decrypt(row.api_key_encrypted) == "sk-new-key-000"


def test_update_provider_not_found(client):
    res = client.put("/api/llm/providers/nope", json={"model": "x"})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "LLM_PROVIDER_NOT_FOUND"


# ---------- 删除 ----------

def test_delete_provider(client):
    client.post("/api/llm/providers", json=PAYLOAD)
    res = client.delete("/api/llm/providers/openai-test")
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True
    # 内存与 DB 同步移除
    assert client.get("/api/llm/providers").json()["data"] == []


def test_delete_provider_with_ai_jobs_conflict(client, registry):
    client.post("/api/llm/providers", json=PAYLOAD)
    # ai_jobs 表（Step 3 已建）插入引用该 provider 的任务
    with registry.db.session() as s:
        s.execute(text(
            "INSERT INTO ai_jobs (id, agent_id, file_path, preset_id, provider_id, status, created_at, updated_at) "
            "VALUES ('job-1', 'alpha', 'SOUL.md', 'p1', 'openai-test', 'applied', 1, 1)"
        ))
        s.commit()
    res = client.delete("/api/llm/providers/openai-test")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "LLM_PROVIDER_CONFLICT"


# ---------- 调用（mock LLMClient，避免真实网络） ----------

async def _fake_chat(self, messages, max_tokens=None, temperature=None):
    return LLMResponse(
        content="pong",
        usage=LLMTokenUsage(prompt_tokens=12, completion_tokens=3, total_tokens=15),
        cost_estimate_usd=0.00021,
    )


def test_chat_endpoint(client, monkeypatch):
    client.post("/api/llm/providers", json=PAYLOAD)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat)
    res = client.post("/api/llm/chat", json={
        "provider_id": "openai-test",
        "messages": [{"role": "user", "content": "ping"}],
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["content"] == "pong"
    assert data["usage"]["total_tokens"] == 15
    assert data["cost_estimate_usd"] == 0.00021


def test_chat_provider_not_found(client):
    res = client.post("/api/llm/chat", json={
        "provider_id": "ghost", "messages": [{"role": "user", "content": "hi"}],
    })
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "LLM_PROVIDER_NOT_FOUND"


def test_test_provider_ok(client, monkeypatch):
    client.post("/api/llm/providers", json=PAYLOAD)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat)
    res = client.post("/api/llm/providers/openai-test/test")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["ok"] is True
    assert data["response_preview"] == "pong"
    assert data["latency_ms"] >= 0


async def _fake_chat_fail(self, messages, max_tokens=None, temperature=None):
    raise RuntimeError("connection refused")


def test_test_provider_failure_reports_ok_false(client, monkeypatch):
    client.post("/api/llm/providers", json=PAYLOAD)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_fail)
    res = client.post("/api/llm/providers/openai-test/test")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["ok"] is False
    assert "connection refused" in data["error"]


def test_test_provider_not_found(client):
    res = client.post("/api/llm/providers/ghost/test")
    assert res.status_code == 404


# ---------- 输出截断（finish_reason）识别 + 自动重试 ----------

def _client(max_tokens: int = 64):
    return LLMClient(LLMProvider(
        id="p1", base_url="http://llm.local/v1", api_key="k", model="m",
        protocol="openai-completions", max_tokens=max_tokens))


def test_truncated_flag_reads_finish_reason():
    """`length`（OpenAI）/ `max_tokens`（Anthropic）= 被额度截断；`stop` / 缺失 = 正常结束。"""
    assert LLMResponse(content="x", finish_reason="length").truncated is True
    assert LLMResponse(content="x", finish_reason="max_tokens").truncated is True
    assert LLMResponse(content="x", finish_reason="stop").truncated is False
    assert LLMResponse(content="x").truncated is False


def test_truncated_output_retries_once_with_doubled_budget(monkeypatch):
    budgets: list[int] = []

    async def fake(self, messages, max_tokens, temperature):
        budgets.append(max_tokens)
        if len(budgets) == 1:
            return LLMResponse(content="半截", usage=LLMTokenUsage(completion_tokens=64),
                               finish_reason="length")
        return LLMResponse(content="写完了", finish_reason="stop")

    monkeypatch.setattr("app.services.llm_registry.LLMClient._complete", fake)
    resp = asyncio.run(_client(64).chat([{"role": "user", "content": "x"}]))
    assert resp.content == "写完了"
    assert budgets == [64, 128]   # 只重试一次，且预算翻倍


def test_persistent_truncation_raises_dedicated_error(monkeypatch):
    async def fake(self, messages, max_tokens, temperature):
        return LLMResponse(content="半截", usage=LLMTokenUsage(completion_tokens=max_tokens),
                           finish_reason="length")

    monkeypatch.setattr("app.services.llm_registry.LLMClient._complete", fake)
    with pytest.raises(LLMOutputTruncatedError) as excinfo:
        asyncio.run(_client(64).chat([{"role": "user", "content": "x"}]))
    assert excinfo.value.code == "LLM_OUTPUT_TRUNCATED"
    # 报的是重试后实际生效的预算，并给出可执行的指引
    assert "128" in str(excinfo.value)
    assert "max_tokens" in str(excinfo.value)


async def _fake_chat_truncated(self, messages, max_tokens=None, temperature=None):
    raise LLMOutputTruncatedError("模型输出被 max_tokens=4096 截断（finish_reason=length），文档没有写完。")


def test_chat_endpoint_maps_truncation_to_422(client, monkeypatch):
    client.post("/api/llm/providers", json=PAYLOAD)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat_truncated)
    res = client.post("/api/llm/chat", json={
        "provider_id": "openai-test",
        "messages": [{"role": "user", "content": "ping"}],
    })
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "LLM_OUTPUT_TRUNCATED"
