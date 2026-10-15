"""In-app notifications.

Created by domain events (validation completing, high-impact changes).
Read and cleared by users through the API.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.notification import Notification
from app.models.user import Role, User

log = logging.getLogger("bimguard.notifications")


def notify(
    db: Session, *, user_id: str, kind: str, title: str,
    body: str = "", link: str = "", project_id: str | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id, project_id=project_id, kind=kind,
        title=title, body=body, link=link,
    )
    db.add(n)
    return n


def _recipient_ids(db: Session, roles: tuple[Role, ...], exclude_user_id: str | None) -> list[str]:
    stmt = select(User.id).where(User.role.in_(roles), User.is_active.is_(True))
    if exclude_user_id:
        stmt = stmt.where(User.id != exclude_user_id)
    return list(db.scalars(stmt))


def notify_roles(
    db: Session, *, project_id: str | None, roles: tuple[Role, ...], kind: str,
    title: str, body: str = "", link: str = "", exclude_user_id: str | None = None,
) -> int:
    """Send one notification to every active user with one of the given roles.

    Returns the number of notifications created. Caller commits.
    """
    count = 0
    for uid in _recipient_ids(db, roles, exclude_user_id):
        notify(db, user_id=uid, kind=kind, title=title, body=body, link=link, project_id=project_id)
        count += 1
    return count


def safe_notify_blocked_run(db: Session, *, project, run, actor: User) -> None:
    """Called after a validation run finishes with status BLOCKED.

    Notifies coordinators, reviewers and admins (excluding the actor).
    Never raises; a notification failure must not break validation.
    """
    try:
        title = f"Validation blocked: {project.name}"
        summary = run.summary or {}
        open_n = summary.get("open", 0)
        blocking = summary.get("blocking", open_n)
        body = f"{blocking} blocking issue{'s' if blocking != 1 else ''} in the latest validation run."
        link = f"/projects/{project.id}/validation"
        count = notify_roles(
            db, project_id=project.id,
            roles=(Role.ADMIN, Role.BIM_COORDINATOR, Role.REVIEWER),
            kind="validation.blocked", title=title, body=body, link=link,
            exclude_user_id=actor.id,
        )
        db.commit()
        log.info("Created %s notifications for blocked run on project %s", count, project.id)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Could not create notifications for blocked run on project %s", project.id)


def list_for_user(
    db: Session, user_id: str, *, unread_only: bool = False, limit: int = 50, offset: int = 0,
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit).offset(offset)
    ))
    return rows, total


def unread_count(db: Session, user_id: str) -> int:
    return int(db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    ) or 0)


def mark_read(db: Session, user_id: str, notification_id: str) -> Notification | None:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        return None
    if row.read_at is None:
        row.read_at = utcnow()
        db.commit()
    return row


def mark_all_read(db: Session, user_id: str) -> int:
    stmt = select(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    now = utcnow()
    count = 0
    for row in db.scalars(stmt):
        row.read_at = now
        count += 1
    if count:
        db.commit()
    return count