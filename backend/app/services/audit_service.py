"""审计日志：所有写操作记录 audit_log 表。"""
from __future__ import annotations

import json

from app.models.db import AuditRow, Database
from app.models.schemas import AuditEntry


class AuditService:
    def __init__(self, db: Database):
        self.db = db

    def record(
        self,
        action: str,
        agent_id: str | None = None,
        target_path: str | None = None,
        details: dict | None = None,
        *,
        user: str = "local",
        result: str = "ok",
    ) -> int:
        with self.db.session() as s:
            row = AuditRow(
                action=action,
                agent_id=agent_id,
                target_path=target_path,
                details_json=json.dumps(details, ensure_ascii=False) if details else None,
                user=user,
                result=result,
            )
            s.add(row)
            s.commit()
            return row.id

    def query(self, *, limit: int = 100, offset: int = 0, agent_id: str | None = None,
              action: str | None = None) -> list[AuditEntry]:
        with self.db.session() as s:
            q = s.query(AuditRow)
            if agent_id:
                q = q.filter(AuditRow.agent_id == agent_id)
            if action:
                q = q.filter(AuditRow.action == action)
            rows = q.order_by(AuditRow.timestamp.desc()).offset(offset).limit(limit).all()
            return [AuditEntry.model_validate(r, from_attributes=True) for r in rows]
