"""DiffService：unified diff / 相似度 / 简易 HTML 高亮。前端用 diff2html 渲染更精细的视图。"""
from __future__ import annotations

import difflib
import html as html_mod

from app.models.schemas import DiffResult
from app.services.backup_service import BackupService
from app.services.file_manager import FileManager


def unified_diff(a_text: str, b_text: str, fromfile: str = "a", tofile: str = "b") -> str:
    return "".join(difflib.unified_diff(
        a_text.splitlines(keepends=True), b_text.splitlines(keepends=True),
        fromfile=fromfile, tofile=tofile,
    ))


def similarity(a_text: str, b_text: str) -> float:
    return round(difflib.SequenceMatcher(None, a_text, b_text).ratio(), 4)


def html_diff(a_text: str, b_text: str, fromfile: str = "a", tofile: str = "b") -> str:
    """把 unified diff 转成带行类名的 <pre>，前端可在此基础上强化。"""
    ud = unified_diff(a_text, b_text, fromfile, tofile)
    lines = []
    for line in ud.rstrip("\n").splitlines():
        cls = "diff-line"
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            cls += " diff-hunk"
        elif line.startswith("+"):
            cls += " diff-add"
        elif line.startswith("-"):
            cls += " diff-del"
        lines.append(f'<span class="{cls}">{html_mod.escape(line)}</span>')
    return "<pre class='diff-view'>" + "\n".join(lines) + "</pre>"


class DiffService:
    def __init__(self, file_manager: FileManager, backup_service: BackupService):
        self.file_manager = file_manager
        self.backup_service = backup_service

    def diff_agents(self, agent_a: str, agent_b: str, file_path: str) -> DiffResult:
        a = self.file_manager.read(agent_a, file_path)
        b = self.file_manager.read(agent_b, file_path)
        return DiffResult(
            agent_a=agent_a, agent_b=agent_b, file=file_path,
            similarity=similarity(a.content, b.content),
            unified_diff=unified_diff(a.content, b.content, fromfile=f"{agent_a}/{file_path}", tofile=f"{agent_b}/{file_path}"),
            html_diff=html_diff(a.content, b.content, fromfile=f"{agent_a}/{file_path}", tofile=f"{agent_b}/{file_path}"),
        )

    def diff_history(self, agent: str, file_path: str, against: int) -> DiffResult:
        current = self.file_manager.read(agent, file_path)
        old = self.backup_service.read_content(against)
        return DiffResult(
            agent_a=agent, agent_b=agent, file=file_path,
            similarity=similarity(current.content, old),
            unified_diff=unified_diff(old, current.content, fromfile=f"backup#{against}", tofile=f"{agent}/{file_path}"),
            html_diff=html_diff(old, current.content, fromfile=f"backup#{against}", tofile=f"{agent}/{file_path}"),
        )
