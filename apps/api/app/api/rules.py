from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.engines.validation import BY_ID, RULES
from app.models.user import Role, User
from app.models.validation import Rule
from app.schemas.validation import RuleOut, RuleUpdate
from app.services import validation as service

router = APIRouter(prefix="/rules", tags=["rules"])
admin_only = require_roles(Role.ADMIN)


def _out(row: Rule) -> RuleOut:
    d = BY_ID[row.rule_id]
    return RuleOut(
        rule_id=row.rule_id, name=d.name, description=d.description, category=d.category, enabled=row.enabled,
        severity=row.severity, params=row.params or {}, default_enabled=d.default_enabled,
        default_severity=d.default_severity, default_params=d.default_params,
        is_default=(row.enabled, row.severity, row.params or {}) == (d.default_enabled, d.default_severity, d.default_params),
        configurable_severity=d.configurable_severity, can_disable=d.can_disable, updated_at=row.updated_at,
        updated_by_name=row.updated_by_name)


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[RuleOut]:
    rows = service.ensure_rules(db)
    return [_out(rows[d.id]) for d in RULES]


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: str, body: RuleUpdate, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> RuleOut:
    return _out(service.update_rule(db, user, rule_id, enabled=body.enabled, severity=body.severity, params=body.params))


@router.post("/{rule_id}/reset", response_model=RuleOut)
def reset_rule(rule_id: str, db: Session = Depends(get_db), user: User = Depends(admin_only)) -> RuleOut:
    return _out(service.reset_rule(db, user, rule_id))
