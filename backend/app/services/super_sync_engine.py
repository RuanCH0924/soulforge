"""超级同步引擎：多个 Agent 之间「同名文件」的秒级双向同步。

冲突策略（已与需求确认）：最新修改优先（双向）。每轮扫描所有参与 Agent 的
选定同名文件，若内容不一致，则以 mtime 最新的那份为「源」，覆盖其余 Agent；
内容已一致则跳过。并列 mtime 时按 Agent id 升序择源，保证确定性。

安全 / 稳定性：
- 只处理配置里显式选中的 Agent 与文件（未选中绝不触碰）；
- 写目标文件走「临时文件 + os.replace」原子替换，避免读到半截内容；
- 用 (mtime, size) 缓存 sha256，未变更的文件不重复读取，降低轮询开销；
- 跳过隐藏目录 / node_modules / 敏感文件；
- 不覆盖 workspace 外部路径（相对路径经 _safe_rel 校验）。
"""
from __future__ import annotations

import difflib
import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services import super_sync_common as ssc

IGNORED_DIR_PARTS = {".git", "node_modules", "__pycache__"}
SENSITIVE_NAMES = {".credentials.md", ".env", ".credentials"}


@dataclass
class FileState:
    agent_id: str
    rel: str
    full_path: Path
    mtime: float
    size: int
    sha256: str


@dataclass
class SyncAction:
    """一次「源 → 目标」的文件同步动作（成功或失败）。"""

    path: str
    source_agent: str
    target_agent: str
    result: str  # ok | failed
    size_bytes: int = 0
    sha256: str = ""
    error: str | None = None
    diff: str | None = None


@dataclass
class EngineStats:
    ticks: int = 0
    synced: int = 0
    last_sync_at: str | None = None
    last_error: str | None = None
    last_duration_ms: int = 0
    actions: list[str] = field(default_factory=list)


def _safe_rel(rel: str) -> str | None:
    """规范化相对路径；拒绝越界 / 绝对路径 / 空路径。"""
    rel = str(rel).replace("\\", "/").strip().lstrip("/")
    if not rel:
        return None
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _is_ignored(rel: str) -> bool:
    parts = rel.split("/")
    if any(part.startswith(".") or part in IGNORED_DIR_PARTS for part in parts):
        return True
    return parts[-1] in SENSITIVE_NAMES


def unified_diff_text(old: str, new: str, rel: str, max_chars: int = 4000) -> str:
    """生成变更内容（unified diff），超长截断，供日志记录「变更内容」。"""
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=2,
        )
    )
    if not diff:
        diff = "（内容差异不在文本层面，可能为二进制）\n"
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n…（diff 已截断）"
    return diff


class SuperSyncEngine:
    def __init__(
        self,
        workspaces: dict[str, Path | str],
        config: dict,
        logger: ssc.SuperSyncLogger | None = None,
    ):
        self.workspaces = {k: Path(v) for k, v in workspaces.items()}
        self.config = ssc.normalize_config(config)
        self.logger = logger
        self.stats = EngineStats()
        self._hash_cache: dict[str, tuple[float, int, str]] = {}

    # ---------------- 扫描 ----------------

    def _hash_file(self, path: Path) -> tuple[float, int, str]:
        """返回 (mtime, size, sha256)；(mtime,size) 未变则复用缓存，避免重复读取。"""
        st = path.stat()
        key = str(path)
        cached = self._hash_cache.get(key)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        entry = (st.st_mtime, st.st_size, sha)
        self._hash_cache[key] = entry
        return entry

    def _list_agent_files(self, agent_id: str) -> list[FileState]:
        workspace = self.workspaces.get(agent_id)
        if workspace is None or not workspace.is_dir():
            return []
        out: list[FileState] = []
        for raw_rel in self.config["files"].get(agent_id, []):
            rel = _safe_rel(raw_rel)
            if rel is None or _is_ignored(rel):
                continue
            full = workspace / rel
            if not full.is_file():
                continue
            try:
                mtime, size, sha = self._hash_file(full)
            except OSError:
                continue
            out.append(FileState(agent_id=agent_id, rel=rel, full_path=full, mtime=mtime, size=size, sha256=sha))
        return out

    def scan(self) -> dict[str, dict[str, FileState]]:
        """返回 {相对路径: {agent_id: FileState}}，仅含参与同步的 Agent / 文件。"""
        scope: dict[str, dict[str, FileState]] = {}
        for agent_id in self.config["agents"]:
            for state in self._list_agent_files(agent_id):
                scope.setdefault(state.rel, {})[agent_id] = state
        return scope

    # ---------------- 同步 ----------------

    def sync_once(self) -> list[SyncAction]:
        """执行一轮同步：按相对路径分组，内容不一致则用最新者覆盖其余。"""
        t0 = time.monotonic()
        scope = self.scan()
        actions: list[SyncAction] = []

        for rel, by_agent in scope.items():
            if len(by_agent) < 2:
                continue  # 只有单个 Agent 存在该文件 → 非同名文件，跳过
            if len({s.sha256 for s in by_agent.values()}) == 1:
                continue  # 内容已一致

            # 最新修改优先；并列时取 agent id 最小者，保证确定性
            source = min(by_agent.values(), key=lambda s: (-s.mtime, s.agent_id))
            try:
                src_bytes = source.full_path.read_bytes()
            except OSError as exc:
                self._log("ERROR", "error", f"读取源文件失败：{rel}", path=rel,
                          source_agent=source.agent_id, target_agent=None, result="failed",
                          error=str(exc))
                self.stats.last_error = f"读取源文件失败 {rel}: {exc}"
                continue
            src_text = src_bytes.decode("utf-8", errors="replace")

            for agent_id, target in by_agent.items():
                if agent_id == source.agent_id or target.sha256 == source.sha256:
                    continue
                try:
                    old_text = target.full_path.read_text(encoding="utf-8", errors="replace")
                    diff = unified_diff_text(old_text, src_text, rel)
                    ssc.atomic_write_file(target.full_path, src_bytes)
                    new_stat = target.full_path.stat()
                    self._hash_cache[str(target.full_path)] = (
                        new_stat.st_mtime, new_stat.st_size, source.sha256,
                    )
                    action = SyncAction(
                        path=rel, source_agent=source.agent_id, target_agent=agent_id,
                        result="ok", size_bytes=len(src_bytes), sha256=source.sha256, diff=diff,
                    )
                    self.stats.synced += 1
                    self._log("INFO", "sync", f"{source.agent_id} → {agent_id} : {rel}",
                              path=rel, source_agent=source.agent_id, target_agent=agent_id,
                              result="ok", size_bytes=len(src_bytes), sha256=source.sha256, diff=diff)
                except OSError as exc:
                    action = SyncAction(
                        path=rel, source_agent=source.agent_id, target_agent=agent_id,
                        result="failed", error=str(exc),
                    )
                    self.stats.last_error = f"写入失败 {rel} → {agent_id}: {exc}"
                    self._log("ERROR", "sync", f"{source.agent_id} → {agent_id} : {rel} 失败",
                              path=rel, source_agent=source.agent_id, target_agent=agent_id,
                              result="failed", error=str(exc))
                actions.append(action)

        self.stats.ticks += 1
        self.stats.last_duration_ms = int((time.monotonic() - t0) * 1000)
        if actions:
            self.stats.last_sync_at = ssc.now_iso()
        return actions

    def run(
        self,
        stop_event: threading.Event,
        heartbeat: Callable[[EngineStats], None] | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        """轮询主循环：每轮 sync_once 后回调心跳，直到 stop_event 置位。"""
        interval = interval_seconds or float(self.config["interval_seconds"])
        while not stop_event.is_set():
            start = time.monotonic()
            try:
                self.sync_once()
            except Exception as exc:  # noqa: BLE001 - 守护循环必须吞掉异常，避免整体退出
                self.stats.last_error = str(exc)
                self._log("ERROR", "error", f"同步轮次异常：{exc}")
            if heartbeat is not None:
                try:
                    heartbeat(self.stats)
                except Exception:  # noqa: BLE001 - 心跳失败不影响同步
                    pass
            delay = interval - (time.monotonic() - start)
            stop_event.wait(max(0.05, delay))

    def _log(self, level: str, event: str, message: str, **fields: Any) -> None:
        if self.logger is not None:
            self.logger.log(level, event, message, **fields)
