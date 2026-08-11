"""SearchService：跨 Agent 全文搜索。优先 ripgrep，不可用时 Python fallback。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from app.config import Config
from app.models.schemas import SearchHit, SearchResult
from app.services.agent_discovery import AgentDiscovery
from app.services.file_manager import FileManager


class SearchService:
    def __init__(self, config: Config, discovery: AgentDiscovery, file_manager: FileManager):
        self.config = config
        self.discovery = discovery
        self.file_manager = file_manager
        self._rg_path: str | None = None

    def _find_ripgrep(self) -> str | None:
        if self._rg_path:
            return self._rg_path
        env_rg = __import__("os").environ.get("SOULFORGE_RG_PATH")
        if env_rg and Path(env_rg).is_file():
            self._rg_path = env_rg
            return env_rg
        found = shutil.which("rg")
        self._rg_path = found
        return found

    def search(self, query: str, *, agent_ids: list[str] | None = None,
               file_patterns: list[str] | None = None, regex: bool = False,
               case_sensitive: bool = True, context_lines: int = 3,
               limit: int = 100) -> SearchResult:
        t0 = time.time()
        if not query:
            return SearchResult(hits=[], total=0, duration_ms=0)
        rg = self._find_ripgrep()
        if rg:
            hits = self._search_ripgrep(rg, query, agent_ids, file_patterns, regex, case_sensitive, context_lines, limit)
        else:
            hits = self._search_python(query, agent_ids, file_patterns, regex, case_sensitive, context_lines, limit)
        duration = int((time.time() - t0) * 1000)
        return SearchResult(hits=hits, total=len(hits), duration_ms=duration)

    def _workspace_dirs(self, agent_ids: list[str] | None) -> list[tuple[str, Path]]:
        """返回 [(agent_id, workspace)]，只保留目录存在的。"""
        agents = self.discovery.discover()
        if agent_ids:
            agents = [a for a in agents if a.id in agent_ids]
        out = []
        for a in agents:
            p = Path(a.workspace)
            if p.is_dir():
                out.append((a.id, p))
        return out

    def _search_ripgrep(self, rg: str, query: str, agent_ids, file_patterns, regex,
                        case_sensitive, context_lines, limit) -> list[SearchHit]:
        dirs = self._workspace_dirs(agent_ids)
        if not dirs:
            return []
        cmd = [rg, "--json", "--no-heading", "--no-config", "--context", str(context_lines)]
        if not case_sensitive:
            cmd.append("--ignore-case")
        cmd.extend(["--glob", "!**/.git/**", "--glob", "!**/node_modules/**", "--glob", "!**/.*"])
        # 限定文件名时只保留用户给的 glob（否则与 *.md 是 OR 关系，过滤失效）
        for pat in (file_patterns or ["*.md"]):
            cmd.extend(["--glob", pat])
        if regex:
            cmd.extend(["--regexp", query])
        else:
            cmd.extend(["--fixed-strings", query])
        cmd.extend(str(p) for _, p in dirs)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError):
            return self._search_python(query, agent_ids, file_patterns, regex, case_sensitive, context_lines, limit)

        agent_by_dir = {str(p): aid for aid, p in dirs}
        hits: list[SearchHit] = []
        # rg --json 事件流：begin / context / match / end
        current: dict[str, object] = {}
        pending_context: list[tuple[int, str]] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type")
            data = evt.get("data", {})
            path = data.get("path", {}).get("text", "")
            if etype == "begin":
                current = {"path": path}
                pending_context = []
            elif etype == "match":
                agent_id = self._agent_for(path, agent_by_dir)
                if agent_id is None:
                    continue
                lines_text = data.get("lines", {}).get("text", "").rstrip("\n")
                lineno = int(data.get("line_number", 0))
                ctx_before = [c for (ln, c) in pending_context if ln < lineno]
                hits.append(SearchHit(
                    agent_id=agent_id, file_path=self._relpath(path, dirs),
                    line_number=lineno, line_content=lines_text,
                    context_before=ctx_before,
                    context_after=[],
                ))
                if len(hits) >= limit:
                    return hits
            elif etype == "context":
                lines_text = data.get("lines", {}).get("text", "").rstrip("\n")
                lineno = int(data.get("line_number", 0))
                pending_context.append((lineno, lines_text))
        return hits

    @staticmethod
    def _norm(p: str) -> str:
        """统一分隔符（Windows 下忽略大小写），用于路径前缀匹配。"""
        return p.replace("\\", "/").lower() if os.name == "nt" else p.replace("\\", "/")

    def _agent_for(self, path: str, agent_by_dir: dict[str, str]) -> str | None:
        np = self._norm(path)
        for d, aid in agent_by_dir.items():
            if np.startswith(self._norm(d)):
                return aid
        return None

    def _relpath(self, path: str, dirs) -> str:
        # dirs 条目为 (agent_id, workspace_path)
        for _, ws in dirs:
            root = Path(ws)
            # os.path.relpath 在 Windows 上按 normcase（忽略大小写）比较，rg 输出可能用小写盘符
            rel = os.path.relpath(path, root)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        return str(path)

    def _search_python(self, query, agent_ids, file_patterns, regex, case_sensitive,
                       context_lines, limit) -> list[SearchHit]:
        import fnmatch

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            if regex:
                matcher = re.compile(query, flags)
            else:
                matcher = re.compile(re.escape(query), flags)
        except re.error:
            return []
        hits: list[SearchHit] = []
        for agent_id, root in self._workspace_dirs(agent_ids):
            for f in self.file_manager.list(agent_id):
                if file_patterns and not any(fnmatch.fnmatch(f.path, p) or fnmatch.fnmatch(Path(f.path).name, p) for p in file_patterns):
                    continue
                content = self.file_manager.read(agent_id, f.path).content
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if matcher.search(line):
                        hits.append(SearchHit(
                            agent_id=agent_id, file_path=f.path, line_number=i + 1,
                            line_content=line.strip(),
                            context_before=[lines[j].strip() for j in range(max(0, i - context_lines), i)],
                            context_after=[lines[j].strip() for j in range(i + 1, min(len(lines), i + 1 + context_lines))],
                        ))
                        if len(hits) >= limit:
                            return hits
        return hits
