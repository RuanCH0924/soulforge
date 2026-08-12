"""集成测试：LLM Provider 接入（M12 · Phase 2.5 Step 2）。

覆盖：CRUD / 密钥加密存储与掩码 / PUT 保留旧 key / 热加载 / 测试连通性（mock）/ 删除保护。
"""
from __future__ import annotations

from sqlalchemy import text

from app.models.db import LLMProviderRow
from app.services.llm_registry import LLMResponse, LLMTokenUsage

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
