"""版本号链路一致性校验（防漂移）。

全项目版本号唯一事实源：`backend/app/__init__.py` 的 `__version__`。
其余出现版本号的位置都必须与它一致，否则发版时极易出现“后端升了、前端没升”之类的不一致。

覆盖：
1. `app.__version__` 符合 SemVer；
2. `backend/pyproject.toml` 的 `project.version` 一致；
3. `frontend/package.json` 与 `frontend/package-lock.json` 一致；
4. API 响应包装 `Meta.version` 一致（`{data, meta}` 的 meta.version）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from app import __version__
from app.models.schemas import Meta

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def test_version_is_semver():
    assert SEMVER_RE.match(__version__), f"__version__ 不符合 SemVer：{__version__}"


def test_pyproject_version_matches():
    with open(PROJECT_ROOT / "backend" / "pyproject.toml", "rb") as f:
        raw = tomllib.load(f)
    assert raw["project"]["version"] == __version__


def test_frontend_package_version_matches():
    pkg_path = PROJECT_ROOT / "frontend" / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    assert pkg["version"] == __version__

    lock_path = PROJECT_ROOT / "frontend" / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock["version"] == __version__
    assert lock["packages"][""]["version"] == __version__


def test_meta_version_uses_single_source():
    assert Meta(timestamp=0).version == __version__
