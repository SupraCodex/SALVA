"""Audit trail of sensitive actions (SEC-08): identifiers and codes only, never secrets."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def record(
    db: Session,
    action: str,
    entity: str,
    entity_id: uuid.UUID | str | None = None,
    *,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail or {},
        )
    )
