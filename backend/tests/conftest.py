"""pytest 共享夹具：临时 openclaw 目录 + 临时数据目录 + 应用客户端。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.services.registry import Registry
from main import create_app

AGENTS_CONFIG = {
    "agents": {
        "defaults": {},
        "list": [
            {"id": "alpha", "workspace": "/root/.openclaw/workspace-alpha"},
            {"id": "beta", "workspace": "workspace-beta"},
        ],
    }
}

CORE_FILES = ["SOUL.md", "AGENTS.md", "IDENTITY.md", "USER.md", "MEMORY.md", "TOOLS.md"]


def _write_md(dir_path: Path, name: str, content: str) -> None:
    p = dir_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture()
def openclaw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "openclaw"
    d.mkdir()
    (d / "openclaw.json").write_text(json.dumps(AGENTS_CONFIG, ensure_ascii=False), encoding="utf-8")

    # alpha：Linux 路径 → 应被映射到 openclaw 根下的 workspace-alpha
    alpha = d / "workspace-alpha"
    alpha.mkdir()
    _write_md(alpha, "SOUL.md", "# alpha SOUL\n\n原则：诚实。")
    _write_md(alpha, "AGENTS.md", "# AGENTS\n\n边界：只动自己的 workspace。")
    _write_md(alpha, "IDENTITY.md", "# IDENTITY\n\n名字：Alpha")
    _write_md(alpha, "USER.md", "# USER\n\n老板偏好：简洁。")
    _write_md(alpha, "MEMORY.md", "# MEMORY\n\n长期事实：Alpha 是测试 Agent。")
    _write_md(alpha, "TOOLS.md", "# TOOLS\n\n可用工具。")
    _write_md(alpha, "memory/2026-08-05.md", "# 2026-08-05\n\n今日结论：……")
    # 敏感文件必须被排除
    _write_md(alpha, ".credentials.md", "secret=xxx")
    _write_md(alpha, ".hidden.md", "hidden")
    # 供搜索测试的独特内容
    _write_md(alpha, "notes/汇报风格.md", "老板要求汇报风格：结论先行，带数据。")

    # beta：相对路径 workspace-beta
    beta = d / "workspace-beta"
    beta.mkdir()
    _write_md(beta, "AGENTS.md", "# AGENTS\n\n边界：beta 只负责运营。")
    _write_md(beta, "SOUL.md", "# beta SOUL\n\n原则：稳定优先。")
    return d


@pytest.fixture()
def config(tmp_path: Path, openclaw_dir: Path) -> Config:
    return Config(
        data_dir=tmp_path / "soulforge-data",
        openclaw_dir=openclaw_dir,
    )


@pytest.fixture()
def registry(config: Config) -> Registry:
    reg = Registry(config)
    reg.startup()
    return reg


@pytest.fixture()
def client(registry: Registry):
    app = create_app(registry)
    with TestClient(app) as c:
        yield c
