"""安全核心：路径校验（_safe_join）、tar 解压防护（safe_extract）。

铁律（见 docs/SECURITY.md）：
- 任何用户提供的路径都必须过 _safe_join()
- tar 解压必须拒绝路径穿越
"""
from __future__ import annotations

import os
import tarfile
from pathlib import Path

from app.core.errors import UnsafePathError


def _safe_join(workspace_root: Path, user_path: str) -> Path:
    """把用户的相对路径安全拼接到 workspace 根，拒绝绝对路径 / .. / 越界。"""
    # 1. 拒绝绝对路径
    if Path(user_path).is_absolute():
        raise UnsafePathError(f"绝对路径禁止：{user_path}")

    # 2. 拒绝路径穿越
    if ".." in Path(user_path).parts:
        raise UnsafePathError(f"相对路径穿越禁止：{user_path}")

    # 3. 解析后必须在 workspace 根下
    root = workspace_root.resolve()
    resolved = (workspace_root / user_path).resolve()
    prefix = str(root) + os.sep
    if not str(resolved).startswith(prefix) and str(resolved) != str(root):
        raise UnsafePathError(f"路径越界：{user_path}")

    return resolved


def safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """安全解压：拒绝 tar 内含路径穿越的成员（tar bomb 防护）。"""
    dest = dest.resolve()
    prefix = str(dest) + os.sep
    for member in tar.getmembers():
        name = member.name
        # 跳过目录自身条目（make_archive 会写入 "." / "./"）
        if name in {"", ".", ".."}:
            continue
        member_path = (dest / name).resolve()
        if not str(member_path).startswith(prefix):
            raise UnsafePathError(f"tar 含路径穿越：{name}")
    tar.extractall(dest)
