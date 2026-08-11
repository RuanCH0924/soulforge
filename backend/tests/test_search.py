"""集成测试：跨 Agent 搜索（ripgrep 优先，Python fallback 兜底）。"""
from __future__ import annotations


def test_search_finds_unique_content(client):
    res = client.post("/api/search", json={"query": "汇报风格"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] >= 1
    hit = data["hits"][0]
    assert hit["agent_id"] == "alpha"
    assert hit["file_path"] == "notes/汇报风格.md"
    assert "结论先行" in hit["line_content"]


def test_search_agent_filter(client):
    res = client.post("/api/search", json={"query": "SOUL", "agent_ids": ["beta"]})
    data = res.json()["data"]
    assert all(h["agent_id"] == "beta" for h in data["hits"])


def test_search_file_pattern(client):
    res = client.post("/api/search", json={"query": "边界", "file_patterns": ["AGENTS.md"]})
    data = res.json()["data"]
    assert all(h["file_path"] == "AGENTS.md" for h in data["hits"])


def test_search_case_sensitive(client):
    res1 = client.post("/api/search", json={"query": "SOUL", "case_sensitive": True})
    res2 = client.post("/api/search", json={"query": "soul", "case_sensitive": False})
    assert res2.json()["data"]["total"] >= res1.json()["data"]["total"]


def test_search_regex(client):
    res = client.post("/api/search", json={"query": r"原则[:：]", "regex": True})
    assert res.status_code == 200
    assert res.json()["data"]["total"] >= 1


def test_search_no_result(client):
    res = client.post("/api/search", json={"query": "zzz_不存在的词_zzz"})
    data = res.json()["data"]
    assert data["total"] == 0
    assert data["hits"] == []
