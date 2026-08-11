"""SyncService：跨 Agent 同步（铁律：plan + confirm 两步，绝不一键覆盖）。"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from app.core.errors import SyncPlanExpiredError, SyncPlanNotFoundError
from app.models.schemas import (
    SyncExecuteResult,
    SyncFilePlan,
    SyncPlanResult,
    SyncResultItem,
)
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.diff_service import html_diff, similarity
from app.services.file_manager import FileManager

PLAN_TTL_SECONDS = 30 * 60  # plan ≤ 30 分钟有效


class SyncService:
    def __init__(self, file_manager: FileManager, backup_service: BackupService, audit: AuditService):
        self.file_manager = file_manager
        self.backup_service = backup_service
        self.audit = audit
        self.plans: dict[str, tuple[float, SyncPlanResult]] = {}

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [pid for pid, (ts, _) in self.plans.items() if now - ts > PLAN_TTL_SECONDS]
        for pid in expired:
            self.plans.pop(pid, None)

    def plan(self, src_agent: str, dst_agent: str, files: list[str]) -> SyncPlanResult:
        self._cleanup_expired()
        items: list[SyncFilePlan] = []
        for f in files:
            src_content = self.file_manager.read(src_agent, f).content
            dst_content = self.file_manager.read(dst_agent, f).content
            items.append(SyncFilePlan(
                path=f,
                similarity=similarity(src_content, dst_content),
                html_diff=html_diff(src_content, dst_content, fromfile=f"{src_agent}/{f}", tofile=f"{dst_agent}/{f}"),
                size_src=len(src_content.encode("utf-8")),
                size_dst=len(dst_content.encode("utf-8")),
            ))
        result = SyncPlanResult(plan_id=str(uuid.uuid4()), src_agent=src_agent, dst_agent=dst_agent, files=items)
        self.plans[result.plan_id] = (time.time(), result)
        return result

    def execute(self, plan_id: str, files: list[str]) -> SyncExecuteResult:
        entry = self.plans.get(plan_id)
        if entry is None:
            raise SyncPlanNotFoundError(f"同步计划不存在或已清理：{plan_id}", details={"plan_id": plan_id})
        created_at, plan = entry
        if time.time() - created_at > PLAN_TTL_SECONDS:
            self.plans.pop(plan_id, None)
            raise SyncPlanExpiredError("同步计划已过期（>30 分钟），请重新生成计划")
        results: list[SyncResultItem] = []
        for f in files:
            src_content = self.file_manager.read(plan.src_agent, f).content
            dst_agent = self.file_manager.require_agent(plan.dst_agent)
            dst_full = Path(dst_agent.workspace) / f
            backup_id = None
            if dst_full.is_file():
                backup_id = self.backup_service.backup(plan.dst_agent, f, dst_full, reason="pre-sync")
            self.file_manager.write(plan.dst_agent, f, src_content, auto_backup=False, audit=False)
            self.audit.record("sync", plan.dst_agent, f,
                              {"src_agent": plan.src_agent, "backup_id": backup_id})
            results.append(SyncResultItem(file=f, status="ok", backup_id=backup_id))
        return SyncExecuteResult(results=results)
