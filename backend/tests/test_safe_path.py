"""单元测试：路径安全 _safe_join（必须覆盖路径穿越用例，见 SECURITY.md 测试要求）。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.errors import UnsafePathError
from app.core.security import _safe_join


def test_normal_join(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    result = _safe_join(root, "SOUL.md")
    assert result == (root / "SOUL.md").resolve()


def test_nested_join(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    result = _safe_join(root, "memory/2026-08-05.md")
    assert result == (root / "memory" / "2026-08-05.md").resolve()


def test_rejects_absolute_path(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(UnsafePathError):
        _safe_join(root, str(tmp_path / "outside.md"))


def test_rejects_parent_traversal(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(UnsafePathError):
        _safe_join(root, "../outside.md")
    with pytest.raises(UnsafePathError):
        _safe_join(root, "a/../../etc/passwd")


def test_encoded_traversal_is_literal_filename(tmp_path: Path):
    """URL 编码的 .. 不会被文件系统解码，应视为普通文件名（安全）。"""
    root = tmp_path / "ws"
    root.mkdir()
    result = _safe_join(root, "..%2F..%2Fetc%2Fpasswd")
    assert result == (root / "..%2F..%2Fetc%2Fpasswd").resolve()


@pytest.mark.skipif(os.name == "nt", reason="Windows 默认无符号链接权限（WinError 1314）")
def test_rejects_escape_via_symlink(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        _safe_join(root, "link/passwd")


def test_allows_workspace_root(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    # 空路径指向 workspace 本身：允许
    result = _safe_join(root, ".")
    assert result == root.resolve()


def test_windows_backslash_traversal(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(UnsafePathError):
        _safe_join(root, "..\\..\\etc\\passwd")
