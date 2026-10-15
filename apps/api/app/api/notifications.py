from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, page_params
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page
from app.schemas.notifications import NotificationOut, UnreadCountOut
from app.services import notifications as service

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> Page[NotificationOut]:
    rows, total = service.list_for_user(
        db, user.id, unread_only=unread_only, limit=page.limit, offset=page.offset
    )
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(r) for r in rows],
        total=total, limit=page.limit, offset=page.offset,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UnreadCountOut:
    return UnreadCountOut(count=service.unread_count(db, user.id))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> NotificationOut:
    row = service.mark_read(db, user.id, notification_id)
    if row is None:
        raise HTTPException(404, "Notification not found.")
    return NotificationOut.model_validate(row)


@router.post("/notifications/read-all", response_model=UnreadCountOut)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UnreadCountOut:
    service.mark_all_read(db, user.id)
    return UnreadCountOut(count=service.unread_count(db, user.id))