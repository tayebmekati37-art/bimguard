from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.projects import get_project_or_404
from app.core.clock import utcnow
from app.db.session import get_db
from app.engines.profiles import ProfileLoadError, list_profiles, load_by_id
from app.models.profile import ProfileActivation
from app.models.user import Role, User
from app.schemas.profiles import (
    ActivateRequest, ActivationOut, ProfileOut, ProfileRuleOut, ProfileSummaryOut,
)
from app.services import audit

router = APIRouter(tags=["profiles"])
can_activate = require_roles(Role.ADMIN, Role.BIM_COORDINATOR)


def _summary(p) -> ProfileSummaryOut:
    return ProfileSummaryOut(
        schema_version=p.schema_version, id=p.id, name=p.name,
        description=p.description, illustrative=p.illustrative,
        rule_count=len(p.rules),
    )


def _full(p) -> ProfileOut:
    return ProfileOut(
        schema_version=p.schema_version, id=p.id, name=p.name,
        description=p.description, illustrative=p.illustrative,
        rules={rid: ProfileRuleOut(enabled=o.enabled, severity=o.severity, params=o.params)
               for rid, o in p.rules.items()},
    )


@router.get("/profiles", response_model=list[ProfileSummaryOut])
def list_all(_user: User = Depends(get_current_user)) -> list[ProfileSummaryOut]:
    return [_summary(p) for p in list_profiles()]


@router.get("/profiles/{profile_id}", response_model=ProfileOut)
def get_one(profile_id: str, _user: User = Depends(get_current_user)) -> ProfileOut:
    profile = load_by_id(profile_id)
    if profile is None:
        raise HTTPException(404, f"Profile {profile_id} not found.")
    return _full(profile)


@router.get("/projects/{project_id}/profile", response_model=ActivationOut)
def current(project_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> ActivationOut:
    get_project_or_404(db, project_id)
    row = db.get(ProfileActivation, project_id)
    if row is None:
        return ActivationOut(project_id=project_id, profile_id=None, activated_at=None, activated_by_name=None)
    return ActivationOut(project_id=project_id, profile_id=row.profile_id,
                         activated_at=row.activated_at, activated_by_name=row.activated_by_name)


@router.put("/projects/{project_id}/profile", response_model=ActivationOut)
def activate(project_id: str, body: ActivateRequest, db: Session = Depends(get_db),
             user: User = Depends(can_activate)) -> ActivationOut:
    project = get_project_or_404(db, project_id)
    try:
        profile = load_by_id(body.profile_id)
    except ProfileLoadError as exc:
        raise HTTPException(422, str(exc)) from exc
    if profile is None:
        raise HTTPException(404, f"Profile {body.profile_id} not found.")
    row = db.get(ProfileActivation, project_id)
    if row is None:
        row = ProfileActivation(project_id=project_id)
        db.add(row)
    row.profile_id = profile.id
    row.activated_at = utcnow()
    row.activated_by_id = user.id
    row.activated_by_name = user.full_name
    audit.record(db, user=user, action="profile.activated", entity_type="project", entity_id=project.id,
                 project_id=project.id, detail={"profile_id": profile.id})
    db.commit()
    return ActivationOut(project_id=project_id, profile_id=row.profile_id,
                         activated_at=row.activated_at, activated_by_name=row.activated_by_name)


@router.delete("/projects/{project_id}/profile", response_model=ActivationOut)
def deactivate(project_id: str, db: Session = Depends(get_db),
               user: User = Depends(can_activate)) -> ActivationOut:
    project = get_project_or_404(db, project_id)
    row = db.get(ProfileActivation, project_id)
    if row is not None:
        db.delete(row)
        audit.record(db, user=user, action="profile.deactivated", entity_type="project",
                     entity_id=project.id, project_id=project.id, detail={"profile_id": row.profile_id})
        db.commit()
    return ActivationOut(project_id=project_id, profile_id=None, activated_at=None, activated_by_name=None)