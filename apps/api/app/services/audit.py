import enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def plain(value: Any) -> Any:
    return value.value if isinstance(value, enum.Enum) else value


def record(
    db: Session, *, user: User | None, action: str, entity_type: str,
    entity_id: str | None = None, project_id: str | None = None, detail: dict | None = None,
) -> None:
    """Adds an audit entry to the current transaction; the caller commits."""
    db.add(AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else "system",
        action=action, entity_type=entity_type, entity_id=entity_id,
        project_id=project_id, detail={k: plain(v) for k, v in (detail or {}).items()},
    ))
