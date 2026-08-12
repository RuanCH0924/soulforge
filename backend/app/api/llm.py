"""路由：LLM Provider 接入（M12 · Phase 2.5 Step 2）。

端点见 docs/API.md §3.12。api_key 加密存储，响应永远只返回掩码。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.api.common import ok
from app.deps import get_registry
from app.models.schemas import LLMChatRequest, LLMProviderCreate, LLMProviderUpdate, LLMResponseOut, LLMTestResult
from app.services.registry import Registry

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers")
def list_providers(reg: Registry = Depends(get_registry)):
    """列出所有 provider（api_key 以掩码返回）。"""
    return ok([p.model_dump() for p in reg.llm.list_providers()])


@router.post("/providers", status_code=201)
def create_provider(body: LLMProviderCreate, reg: Registry = Depends(get_registry)):
    """新增 provider（api_key 加密存储，热加载生效）。"""
    return ok(reg.llm.create_provider(body).model_dump())


@router.put("/providers/{provider_id}")
def update_provider(provider_id: str, body: LLMProviderUpdate, reg: Registry = Depends(get_registry)):
    """编辑 provider。api_key 留空 = 保留旧 key（热加载生效）。"""
    return ok(reg.llm.update_provider(provider_id, body).model_dump())


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str, reg: Registry = Depends(get_registry)):
    """删除 provider；被 ai_jobs 引用 → 409。"""
    reg.llm.delete_provider(provider_id)
    return ok({"id": provider_id, "deleted": True})


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, reg: Registry = Depends(get_registry)):
    """测试连通性：发一条 ping，返回耗时与回复预览。"""
    client = reg.llm.get_client(provider_id)
    t0 = time.time()
    try:
        resp = await client.chat([{"role": "user", "content": "ping"}], max_tokens=16, temperature=0.0)
        latency_ms = int((time.time() - t0) * 1000)
        return ok(LLMTestResult(
            ok=True, latency_ms=latency_ms, response_preview=resp.content[:200]).model_dump())
    except Exception as e:  # 连通性测试：失败不抛错，返回 ok=false + 原因
        latency_ms = int((time.time() - t0) * 1000)
        return ok(LLMTestResult(ok=False, latency_ms=latency_ms, response_preview="", error=str(e)).model_dump())


@router.post("/chat")
async def chat(body: LLMChatRequest, reg: Registry = Depends(get_registry)):
    """通用 chat 端点（内部用，AI Editor 调用）。"""
    client = reg.llm.get_client(body.provider_id)
    resp = await client.chat(
        [m.model_dump() for m in body.messages],
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )
    return ok(LLMResponseOut(
        content=resp.content, usage=resp.usage, cost_estimate_usd=resp.cost_estimate_usd).model_dump())
