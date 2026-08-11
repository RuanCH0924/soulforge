"""FileManager：封装所有 workspace 文件读写，自动触发备份 + 审计 + 索引。

安全约束：所有路径过 _safe_join()；写前自动备份；删除走 send2trash。
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import send2trash

from app.config import Config
from app.core.errors import ConflictError, FileNotFoundError, UnsafePathError
from app.core.security import _safe_join
from app.models.db import AgentRow, Database, FileRow
from app.models.schemas import (
    AgentInfo,
    FileContent,
    FileInfo,
    RollbackResult,
    ScanResult,
    WriteResult,
)
from app.services.agent_discovery import AgentDiscovery
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService

CORE_FILES = {
    "SOUL.md", "AGENTS.md", "IDENTITY.md", "USER.md",
    "TOOLS.md", "MEMORY.md", "HEARTBEAT.md", "DREAMS.md",
}
SENSITIVE_NAMES = {".credentials.md", ".env"}


def classify_role(workspace_root: Path, file_path: Path) -> str:
    """按 docs/DATA-MODEL.md 的规则给文件打 role 标签。"""
    rel = file_path.relative_to(workspace_root)
    parts = rel.parts
    if len(parts) == 1 and parts[0] in CORE_FILES:
        return "CORE"
    if len(parts) >= 2 and parts[0] == "memory" and parts[1].endswith(".md"):
        return "MEMORY"
    if len(parts) >= 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
        return "SKILL"
    if rel.name in {"openclaw.json", ".credentials.md"} or rel.name.startswith("."):
        return "META"
    return "OTHER"


class FileManager:
    def __init__(self, config: Config, db: Database, discovery: AgentDiscovery,
                 backup: BackupService, audit: AuditService):
        self.config = config
        self.db = db
        self.discovery = discovery
        self.backup = backup
        self.audit = audit

    # ---------- 辅助 ----------

    def require_agent(self, agent_id: str) -> AgentInfo:
        return self.discovery.require(agent_id)

    def _resolve(self, agent_id: str, path: str) -> Path:
        agent = self.require_agent(agent_id)
        return _safe_join(Path(agent.workspace), path)

    def _should_include(self, rel: Path) -> bool:
        if any(part.startswith(".") for part in rel.parts):
            return False  # 隐藏目录 / 文件（.git / .clawhub / .learnings / .credentials.md 等）
        if "node_modules" in rel.parts:
            return False
        return rel.name not in SENSITIVE_NAMES

    def _build_file_info(self, agent_id: str, rel: str, full: Path, role: str) -> FileInfo:
        stat = full.stat()
        return FileInfo(
            path=rel,
            role=role,
            size_bytes=stat.st_size,
            mtime=int(stat.st_mtime),
            sha256=hashlib.sha256(full.read_bytes()).hexdigest(),
        )

    # ---------- 读 ----------

    def list(self, agent_id: str) -> list[FileInfo]:
        """列出 workspace 下所有可管理的 .md 文件（含 role / 元数据）。"""
        agent = self.require_agent(agent_id)
        root = Path(agent.workspace)
        if not root.is_dir():
            return []
        files: list[FileInfo] = []
        for p in root.rglob("*.md"):
            rel = p.relative_to(root)
            if not self._should_include(rel):
                continue
            rel_str = rel.as_posix()
            info = self._build_file_info(agent_id, rel_str, p, classify_role(root, p))
            files.append(info)
        files.sort(key=lambda f: f.path)
        return files

    def list_paths(self, agent_id: str) -> list[str]:
        """轻量版：只返回相对路径列表，不读文件内容（lint 等场景避免全量哈希）。"""
        agent = self.require_agent(agent_id)
        root = Path(agent.workspace)
        if not root.is_dir():
            return []
        out = []
        for p in root.rglob("*.md"):
            rel = p.relative_to(root)
            if self._should_include(rel):
                out.append(rel.as_posix())
        return sorted(out)

    def read_text(self, agent_id: str, path: str) -> str:
        """轻量版：只读文本内容，不算 sha256 / role（lint 内部用）。"""
        agent = self.require_agent(agent_id)
        full = _safe_join(Path(agent.workspace), path)
        if not full.is_file():
            raise FileNotFoundError(f"{agent_id} workspace 下找不到 {path}",
                                    details={"agent_id": agent_id, "path": path})
        return full.read_text(encoding="utf-8", errors="replace")

    def read(self, agent_id: str, path: str) -> FileContent:
        agent = self.require_agent(agent_id)
        root = Path(agent.workspace)
        full = _safe_join(root, path)
        if not full.is_file():
            raise FileNotFoundError(
                f"{agent_id} workspace 下找不到 {path}",
                details={"agent_id": agent_id, "path": path},
            )
        content = full.read_text(encoding="utf-8", errors="replace")
        stat = full.stat()
        return FileContent(
            agent_id=agent_id,
            path=path,
            role=classify_role(root, full),
            content=content,
            size_bytes=stat.st_size,
            mtime=int(stat.st_mtime),
            sha256=hashlib.sha256(full.read_bytes()).hexdigest(),
        )

    # ---------- 写 ----------

    def write(self, agent_id: str, path: str, content: str, *,
              auto_backup: bool = True, reason: str = "auto-write",
              audit: bool = True, expected_sha256: str | None = None) -> WriteResult:
        agent = self.require_agent(agent_id)
        root = Path(agent.workspace)
        full = _safe_join(root, path)
        exists = full.is_file()

        # 乐观锁：期望旧 hash
        if expected_sha256 and exists:
            current = hashlib.sha256(full.read_bytes()).hexdigest()
            if current != expected_sha256:
                raise ConflictError(
                    f"文件已被外部修改，请刷新后再保存（期望 {expected_sha256[:8]}…，实际 {current[:8]}…）",
                    details={"agent_id": agent_id, "path": path},
                )

        backup_id = None
        if exists and auto_backup and self.config.backup.auto_backup_on_write:
            backup_id = self.backup.backup(agent_id, path, full, reason=reason)

        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

        stat = full.stat()
        sha = hashlib.sha256(full.read_bytes()).hexdigest()
        if audit:
            self.audit.record("write", agent_id, path, {"size_after": stat.st_size, "backup_id": backup_id})
        self._upsert_file_row(agent_id, path, sha, stat.st_size, int(stat.st_mtime))
        return WriteResult(
            agent_id=agent_id,
            path=path,
            size_bytes=stat.st_size,
            mtime=int(stat.st_mtime),
            sha256=sha,
            backup_id=backup_id,
        )

    def rollback(self, agent_id: str, file_path: str, backup_id: int) -> RollbackResult:
        """回滚：先备份当前状态（pre-rollback），再写入历史内容。"""
        agent = self.require_agent(agent_id)
        root = Path(agent.workspace)
        full = _safe_join(root, file_path)
        current_backup_id = None
        if full.is_file():
            current_backup_id = self.backup.backup(agent_id, file_path, full, reason="pre-rollback")
        content = self.backup.read_content(backup_id)
        result = self.write(agent_id, file_path, content, auto_backup=False, audit=False)
        self.audit.record(
            "rollback", agent_id, file_path,
            {"from_backup": current_backup_id, "to_backup": backup_id},
        )
        return RollbackResult(
            file_path=file_path,
            rolled_back_to=backup_id,
            new_backup_id=current_backup_id or 0,
            sha256=result.sha256,
        )

    def delete(self, agent_id: str, path: str) -> None:
        """删除走 send2trash，绝不 os.remove（可恢复）。"""
        agent = self.require_agent(agent_id)
        root = Path(agent.workspace)
        full = _safe_join(root, path)
        if not full.exists():
            raise FileNotFoundError(f"文件不存在：{path}", details={"agent_id": agent_id, "path": path})
        if full.resolve() == root.resolve():
            raise UnsafePathError("禁止删除 workspace 根目录")
        send2trash.send2trash(str(full))
        with self.db.session() as s:
            s.query(FileRow).filter(FileRow.agent_id == agent_id, FileRow.path == path).delete()
            s.commit()
        self.audit.record("delete", agent_id, path)

    # ---------- 索引 ----------

    def _upsert_file_row(self, agent_id: str, path: str, sha: str, size: int, mtime: int, role: str | None = None) -> None:
        with self.db.session() as s:
            row = s.query(FileRow).filter(FileRow.agent_id == agent_id, FileRow.path == path).first()
            if row is None:
                s.add(FileRow(agent_id=agent_id, path=path, role=role or classify_role_by_agent_path(self, agent_id, path),
                              size_bytes=size, mtime=mtime, sha256=sha))
            else:
                row.size_bytes = size
                row.mtime = mtime
                row.sha256 = sha
                if role:
                    row.role = role
            s.commit()

    def scan_all(self) -> ScanResult:
        """重新扫描全部 Agent：重建 files 表 + 更新 agents 表缓存。"""
        t0 = time.time()
        agents = self.discovery.discover()
        total = 0
        with self.db.session() as s:
            for a in agents:
                s.query(FileRow).filter(FileRow.agent_id == a.id).delete()
                files = self.list(a.id)
                total += len(files)
                for f in files:
                    s.add(FileRow(agent_id=a.id, path=f.path, role=f.role, size_bytes=f.size_bytes,
                                  mtime=f.mtime, sha256=f.sha256, lint_warnings=f.lint_warnings))
                row = s.get(AgentRow, a.id)
                now = int(time.time())
                if row is None:
                    s.add(AgentRow(id=a.id, workspace=a.workspace, display_name=a.display_name,
                                   file_count=len(files), last_scanned_at=now))
                else:
                    row.workspace = a.workspace
                    row.display_name = a.display_name
                    row.file_count = len(files)
                    row.last_scanned_at = now
            s.commit()
        return ScanResult(agents_scanned=len(agents), files_indexed=total, duration_ms=int((time.time() - t0) * 1000))

    def list_agents(self) -> list[AgentInfo]:
        """DB 缓存的 Agent 列表（含 file_count / 扫描时间）。"""
        with self.db.session() as s:
            rows = s.query(AgentRow).all()
            if not rows:
                return self.discovery.discover()
            by_id = {r.id: r for r in rows}
            result = []
            for a in self.discovery.discover():
                r = by_id.get(a.id)
                result.append(AgentInfo(
                    id=a.id, workspace=a.workspace, display_name=a.display_name or a.id,
                    file_count=r.file_count if r else 0, last_scanned_at=r.last_scanned_at if r else None,
                    created_at=r.created_at if r else None, updated_at=r.updated_at if r else None,
                ))
            return result


def classify_role_by_agent_path(file_manager: FileManager, agent_id: str, path: str) -> str:
    """根据 agent 的 workspace 根 + 相对路径判定 role。"""
    agent = file_manager.require_agent(agent_id)
    root = Path(agent.workspace)
    return classify_role(root, root / path)
