"""集成测试：Agent 发现（含 Linux 路径映射）与文件浏览。"""
from __future__ import annotations

from pathlib import Path


def test_list_agents(client, openclaw_dir: Path):
    res = client.get("/api/agents")
    assert res.status_code == 200
    body = res.json()
    data = body["data"]
    assert len(data) == 2
    by_id = {a["id"]: a for a in data}
    # alpha 的 Linux 路径被映射到 openclaw 根下的 workspace-alpha
    assert by_id["alpha"]["workspace"] == str((openclaw_dir / "workspace-alpha").resolve())
    assert by_id["beta"]["workspace"] == str((openclaw_dir / "workspace-beta").resolve())
    # 文件数：alpha 有 7 个 md（含 memory + notes），排除 .credentials.md / .hidden.md
    assert by_id["alpha"]["file_count"] == 8
    assert by_id["beta"]["file_count"] == 2


def test_scan_endpoint(client):
    res = client.post("/api/agents/scan")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agents_scanned"] == 2
    assert data["files_indexed"] >= 8


def test_get_agent_detail(client):
    res = client.get("/api/agents/alpha")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["id"] == "alpha"
    assert len(data["recent_files"]) >= 1


def test_get_agent_not_found(client):
    res = client.get("/api/agents/ghost")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "AGENT_NOT_FOUND"


def test_list_files_with_role(client):
    res = client.get("/api/agents/alpha/files")
    assert res.status_code == 200
    files = res.json()["data"]
    roles = {f["path"]: f["role"] for f in files}
    assert roles["SOUL.md"] == "CORE"
    assert roles["memory/2026-08-05.md"] == "MEMORY"
    assert roles["notes/汇报风格.md"] == "OTHER"
    # 敏感文件不进列表
    assert ".credentials.md" not in roles
    assert ".hidden.md" not in roles


def test_read_file(client):
    res = client.get("/api/agents/alpha/files/SOUL.md")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["agent_id"] == "alpha"
    assert "alpha SOUL" in data["content"]
    assert data["role"] == "CORE"
    assert data["sha256"]


def test_read_missing_file_404(client):
    res = client.get("/api/agents/alpha/files/NOPE.md")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_path_traversal_rejected(client):
    """URL 编码的路径穿越必须被拒（服务层 _safe_join 已全覆盖，此处验证 API 不泄露文件）。"""
    res = client.get("/api/agents/alpha/files/%2e%2e%2fetc%2fpasswd")
    assert res.status_code != 200
    assert "root:" not in res.text  # 绝不返回系统文件内容
