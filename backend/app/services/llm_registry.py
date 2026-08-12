"""LLMRegistry + LLMClient（M12 · LLM Provider 接入，Phase 2.5 Step 2）。

- LLMRegistry：管理 llm_providers 注册表，配置变更热加载（不重启服务）
- LLMClient：httpx 异步调用，支持 openai-completions / anthropic-messages 两种协议
- API key 只在内存中解密使用，DB 只存 Fernet 密文（KeyVault）
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy import inspect, text

from app.core.errors import (
    LLMRequestError,
    ProviderConflictError,
    ProviderNotFoundError,
    UnsupportedProtocolError,
)
from app.core.key_vault import KeyVault
from app.models.db import Database, LLMProviderRow
from app.models.schemas import (
    LLMProviderCreate,
    LLMProviderOut,
    LLMProviderUpdate,
    LLMTokenUsage,
)

ANTHROPIC_VERSION = "2023-06-01"


@dataclass
class LLMProvider:
    id: str
    base_url: str
    api_key: str
    model: str
    protocol: str
    enabled: bool = True
    max_tokens: int = 4096
    temperature: float = 0.3
    timeout_seconds: int = 60


@dataclass
class LLMResponse:
    content: str
    usage: LLMTokenUsage = field(default_factory=LLMTokenUsage)
    cost_estimate_usd: float = 0.0


# 成本估算（粗粒度）：prompt $0.01/M token、completion $0.03/M token，量级参考 GPT-4o
_PROMPT_PER_1K = 0.01 / 1000
_COMPLETION_PER_1K = 0.03 / 1000


def _estimate_cost(usage: LLMTokenUsage) -> float:
    return round(usage.prompt_tokens * _PROMPT_PER_1K + usage.completion_tokens * _COMPLETION_PER_1K, 6)


class LLMClient:
    """单 provider 的 LLM 调用客户端，按 protocol 分发到对应适配器。"""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def chat(self, messages: list[dict], max_tokens: int | None = None,
                   temperature: float | None = None) -> LLMResponse:
        if self.provider.protocol == "openai-completions":
            return await self._openai_completions(messages, max_tokens, temperature)
        if self.provider.protocol == "anthropic-messages":
            return await self._anthropic_messages(messages, max_tokens, temperature)
        raise UnsupportedProtocolError(f"不支持的协议：{self.provider.protocol}")

    async def _openai_completions(self, messages: list[dict], max_tokens: int | None,
                                  temperature: float | None) -> LLMResponse:
        url = self.provider.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.provider.model,
            "messages": messages,
            "max_tokens": max_tokens or self.provider.max_tokens,
            "temperature": temperature if temperature is not None else self.provider.temperature,
        }
        headers = {"Authorization": f"Bearer {self.provider.api_key}", "Content-Type": "application/json"}
        data = await self._post(url, headers, payload)
        content = data["choices"][0]["message"]["content"]
        u = data.get("usage", {})
        usage = LLMTokenUsage(
            prompt_tokens=u.get("prompt_tokens", 0),
            completion_tokens=u.get("completion_tokens", 0),
            total_tokens=u.get("total_tokens", 0),
        )
        return LLMResponse(content=content, usage=usage, cost_estimate_usd=_estimate_cost(usage))

    async def _anthropic_messages(self, messages: list[dict], max_tokens: int | None,
                                  temperature: float | None) -> LLMResponse:
        base = self.provider.base_url.rstrip("/")
        url = (base if base.endswith("/v1") else base + "/v1") + "/messages"
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        payload = {
            "model": self.provider.model,
            "max_tokens": max_tokens or self.provider.max_tokens,
            "temperature": temperature if temperature is not None else self.provider.temperature,
            "messages": user_msgs,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        headers = {
            "x-api-key": self.provider.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        data = await self._post(url, headers, payload)
        content = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        u = data.get("usage", {})
        prompt = u.get("input_tokens", 0)
        completion = u.get("output_tokens", 0)
        usage = LLMTokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)
        return LLMResponse(content=content, usage=usage, cost_estimate_usd=_estimate_cost(usage))

    async def _post(self, url: str, headers: dict, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise LLMRequestError(f"请求 {url} 失败：{e}", details={"provider": self.provider.id}) from e
        if resp.status_code >= 400:
            raise LLMRequestError(
                f"{self.provider.protocol} 调用失败（HTTP {resp.status_code}）：{resp.text[:300]}",
                details={"provider": self.provider.id, "status": resp.status_code},
            )
        return resp.json()


class LLMRegistry:
    """llm_providers 注册表：内存态 + DB 持久化，支持热加载。"""

    def __init__(self, db: Database, key_vault: KeyVault):
        self.db = db
        self.key_vault = key_vault
        self._providers: dict[str, LLMProvider] = {}
        self._lock = asyncio.Lock()

    # ---------- 映射 ----------

    def _row_to_provider(self, row: LLMProviderRow) -> LLMProvider:
        return LLMProvider(
            id=row.id, base_url=row.base_url, api_key=self.key_vault.decrypt(row.api_key_encrypted),
            model=row.model, protocol=row.protocol, enabled=bool(row.enabled),
            max_tokens=row.max_tokens, temperature=row.temperature, timeout_seconds=row.timeout_seconds,
        )

    @staticmethod
    def _mask_key(api_key: str) -> str:
        if len(api_key) <= 8:
            return "****"
        return api_key[:3] + "****" + api_key[-4:]

    def _row_to_out(self, row: LLMProviderRow) -> LLMProviderOut:
        return LLMProviderOut(
            id=row.id, base_url=row.base_url, api_key_masked=self._mask_key(self.key_vault.decrypt(row.api_key_encrypted)),
            model=row.model, protocol=row.protocol, enabled=bool(row.enabled),
            max_tokens=row.max_tokens, temperature=row.temperature, timeout_seconds=row.timeout_seconds,
            created_at=row.created_at, updated_at=row.updated_at,
        )

    def _get_row(self, session, provider_id: str) -> LLMProviderRow:
        row = session.get(LLMProviderRow, provider_id)
        if row is None:
            raise ProviderNotFoundError(f"Provider 不存在：{provider_id}", details={"provider_id": provider_id})
        return row

    # ---------- 加载 / 热加载 ----------

    def load_from_db(self) -> None:
        """启动时从 llm_providers 表加载到内存。"""
        with self.db.session() as s:
            rows = s.query(LLMProviderRow).all()
            for row in rows:
                self._providers[row.id] = self._row_to_provider(row)

    def reload_one(self, provider_id: str) -> None:
        """热加载单个 provider（POST/PUT/DELETE 后调用，不重启）。"""
        with self.db.session() as s:
            row = s.get(LLMProviderRow, provider_id)
        if row is None:
            self._providers.pop(provider_id, None)
            return
        self._providers[provider_id] = self._row_to_provider(row)

    def reload_all(self) -> None:
        self._providers.clear()
        self.load_from_db()

    # ---------- 查询 / CRUD ----------

    def list_providers(self) -> list[LLMProviderOut]:
        with self.db.session() as s:
            rows = s.query(LLMProviderRow).order_by(LLMProviderRow.created_at).all()
            return [self._row_to_out(r) for r in rows]

    def create_provider(self, payload: LLMProviderCreate) -> LLMProviderOut:
        now = int(time.time())
        with self.db.session() as s:
            row = LLMProviderRow(
                id=payload.id, base_url=payload.base_url,
                api_key_encrypted=self.key_vault.encrypt(payload.api_key),
                model=payload.model, protocol=payload.protocol, enabled=int(payload.enabled),
                max_tokens=payload.max_tokens, temperature=payload.temperature,
                timeout_seconds=payload.timeout_seconds, created_at=now, updated_at=now,
            )
            s.add(row)
            s.commit()
        self.reload_one(payload.id)
        return self._row_to_out(row)

    def update_provider(self, provider_id: str, payload: LLMProviderUpdate) -> LLMProviderOut:
        """编辑 provider。api_key 留空/None = 保留旧 key。"""
        with self.db.session() as s:
            row = self._get_row(s, provider_id)
            if payload.base_url is not None:
                row.base_url = payload.base_url
            if payload.api_key:  # 非空才更换密钥
                row.api_key_encrypted = self.key_vault.encrypt(payload.api_key)
            if payload.model is not None:
                row.model = payload.model
            if payload.protocol is not None:
                row.protocol = payload.protocol
            if payload.enabled is not None:
                row.enabled = int(payload.enabled)
            if payload.max_tokens is not None:
                row.max_tokens = payload.max_tokens
            if payload.temperature is not None:
                row.temperature = payload.temperature
            if payload.timeout_seconds is not None:
                row.timeout_seconds = payload.timeout_seconds
            row.updated_at = int(time.time())
            s.commit()
            out = self._row_to_out(row)
        self.reload_one(provider_id)
        return out

    def _ai_jobs_count(self, provider_id: str) -> int:
        """ai_jobs 表（Step 3）尚未存在时跳过；存在则统计引用数防断链。"""
        with self.db.session() as s:
            if "ai_jobs" not in inspect(s.bind).get_table_names():
                return 0
            return s.execute(
                text("SELECT COUNT(*) FROM ai_jobs WHERE provider_id = :pid"), {"pid": provider_id}
            ).scalar() or 0

    def delete_provider(self, provider_id: str) -> None:
        """删除 provider；被 ai_jobs 引用 → 409。"""
        with self.db.session() as s:
            row = self._get_row(s, provider_id)
            refs = self._ai_jobs_count(provider_id)
            if refs > 0:
                raise ProviderConflictError(
                    f"Provider 已被 {refs} 个 AI 任务引用，禁止删除（避免历史断链）",
                    details={"provider_id": provider_id, "ai_jobs": refs},
                )
            s.delete(row)
            s.commit()
        self._providers.pop(provider_id, None)

    def get_provider(self, provider_id: str) -> LLMProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"Provider 不存在：{provider_id}", details={"provider_id": provider_id})
        if not provider.enabled:
            raise ProviderNotFoundError(f"Provider 已禁用：{provider_id}", details={"provider_id": provider_id})
        return provider

    def get_client(self, provider_id: str) -> LLMClient:
        return LLMClient(self.get_provider(provider_id))
