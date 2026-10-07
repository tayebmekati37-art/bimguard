from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, page_params, require_roles
from app.core.clock import utcnow
from app.db.session import get_db
from app.models.document import Document
from app.models.project import Project, ProjectStatus
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import audit, storage

router = APIRouter(prefix="/projects", tags=["projects"])
manage = require_roles(Role.ADMIN, Role.BIM_COORDINATOR)
admin_only = require_roles(Role.ADMIN)


def get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found. It may have been deleted.")
    return project


def _with_count(db: Session, projects: list[Project]) -> list[ProjectOut]:
    counts: dict[str, int] = {}
    if projects:
        rows = db.execute(
            select(Document.project_id, func.count()).where(Document.project_id.in_([p.id for p in projects]))
            .group_by(Document.project_id)
        ).all()
        counts = {pid: n for pid, n in rows}
    return [ProjectOut.model_validate(p).model_copy(update={"document_count": counts.get(p.id, 0)}) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(manage)) -> ProjectOut:
    project = Project(**body.model_dump(), created_by_id=user.id)
    db.add(project)
    db.flush()
    audit.record(db, user=user, action="project.created", entity_type="project", entity_id=project.id,
                 project_id=project.id, detail={"name": project.name})
    db.commit()
    return _with_count(db, [project])[0]


@router.get("", response_model=Page[ProjectOut])
def list_projects(
    status_filter: ProjectStatus | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=100),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> Page[ProjectOut]:
    stmt = select(Project)
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Project.name.ilike(like) | Project.client.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Project.updated_at.desc()).limit(page.limit).offset(page.offset)).all()
    return Page[ProjectOut](items=_with_count(db, list(rows)), total=total, limit=page.limit, offset=page.offset)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> ProjectOut:
    return _with_count(db, [get_project_or_404(db, project_id)])[0]


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str, body: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(manage)
) -> ProjectOut:
    project = get_project_or_404(db, project_id)
    changes: dict = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None or getattr(project, field) == value:
            continue
        changes[field] = {"old": audit.plain(getattr(project, field)), "new": audit.plain(value)}
        setattr(project, field, value)
    if changes:
        project.updated_at = utcnow()
        action = "project.updated"
        if "status" in changes:
            action = "project.archived" if project.status == ProjectStatus.ARCHIVED else "project.restored"
        audit.record(db, user=user, action=action, entity_type="project", entity_id=project.id,
                     project_id=project.id, detail=changes)
        db.commit()
    return _with_count(db, [project])[0]


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> None:
    project = get_project_or_404(db, project_id)
    audit.record(db, user=user, action="project.deleted", entity_type="project", entity_id=project.id,
                 project_id=project.id, detail={"name": project.name})
    db.delete(project)
    db.commit()
    storage.delete_project_files(project_id)
