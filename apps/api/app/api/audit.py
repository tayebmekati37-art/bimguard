from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, page_params, require_roles
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.document import AuditOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])
can_read_audit = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.REVIEWER)


@router.get("", response_model=Page[AuditOut])
def list_audit_logs(
    project_id: str | None = None,
    action: str | None = Query(None, max_length=64),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(can_read_audit),
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    if project_id:
        stmt = stmt.where(AuditLog.project_id == project_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(page.limit).offset(page.offset)).all()
    items = [AuditOut.model_validate(r) for r in rows]
    return Page[AuditOut](items=items, total=total, limit=page.limit, offset=page.offset)
