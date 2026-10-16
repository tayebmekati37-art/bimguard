import time
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.engines.validation import (
    AffectedRef, DocumentState, ElementReferences, OpenImpact, RevisionState, RuleConfig, Snapshot, RULES,
    assess, blocking_severity, run_rules, validate_configuration,
)
from app.models.bim import BimElement
from app.models.dependency import Dependency
from app.models.document import Document, DocumentRevision
from app.models.impact import ImpactEvent
from app.models.user import User
from app.models.validation import IssueAcknowledgement, Rule, ValidationIssue, ValidationRun
from app.services import audit
from app.services import dependencies as dependency_service
from app.services import impact as impact_service
from app.engines.validation.definitions import BY_ID
from app.engines.profiles import registry as profile_registry
from app.models.profile import ProfileActivation

MAX_ELEMENTS_PER_DOCUMENT = 50000


# ------------------------------------------------------------------ rule configuration
def ensure_rules(db: Session) -> dict[str, Rule]:
    """Creates any missing rule row from the factory defaults. Existing configuration is never overwritten."""
    rows = {r.rule_id: r for r in db.scalars(select(Rule))}
    created = False
    for definition in RULES:
        if definition.id not in rows:
            row = Rule(rule_id=definition.id, enabled=definition.default_enabled, severity=definition.default_severity,
                       params=dict(definition.default_params))
            db.add(row)
            rows[definition.id] = row
            created = True
    if created:
        db.commit()
    return rows


def rule_configs(db: Session, project_id: str | None = None) -> dict[str, RuleConfig]:
    """Return the effective rule configuration.

    Order of precedence, highest last:
      1. Factory defaults
      2. Per-rule database overrides (from the rules page)
      3. Active profile for the project (if any)
    """
    base = {rid: RuleConfig(rid, row.enabled, row.severity, row.params or {})
            for rid, row in ensure_rules(db).items()}
    if project_id is None:
        return base
    activation = db.scalar(select(ProfileActivation).where(ProfileActivation.project_id == project_id))
    if activation is None:
        return base
    profile = profile_registry.load_by_id(activation.profile_id)
    if profile is None:
        # The profile file was removed since activation; fall back silently.
        return base
    merged = dict(base)
    for rule_id, override in profile.rules.items():
        if rule_id not in merged:
            continue
        cfg = merged[rule_id]
        merged[rule_id] = RuleConfig(
            rule_id,
            override.enabled if override.enabled is not None else cfg.enabled,
            override.severity if override.severity is not None else cfg.severity,
            override.params if override.params is not None else cfg.params,
        )
    return merged


def update_rule(db: Session, user: User, rule_id: str, *, enabled: bool | None, severity: str | None,
                params: dict | None) -> Rule:
    rows = ensure_rules(db)
    definition = BY_ID.get(rule_id)
    if definition is None:
        raise HTTPException(404, f"Unknown rule {rule_id}.")
    if enabled is False and not definition.can_disable:
        raise HTTPException(422, f"{definition.name} cannot be disabled.")
    if severity is not None and not definition.configurable_severity:
        raise HTTPException(422, f"The severity of {definition.name} is not configurable.")
    try:
        validate_configuration(rule_id, severity, params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = rows[rule_id]
    changes: dict = {}
    for name, value in (("enabled", enabled), ("severity", severity), ("params", params)):
        if value is not None and getattr(row, name) != value:
            changes[name] = {"old": getattr(row, name), "new": value}
            setattr(row, name, value)
    if changes:
        row.updated_at, row.updated_by_name = utcnow(), user.full_name
        audit.record(db, user=user, action="rule.updated", entity_type="rule", entity_id=rule_id, detail=changes)
        db.commit()
    return row


def reset_rule(db: Session, user: User, rule_id: str) -> Rule:
    definition = BY_ID.get(rule_id)
    if definition is None:
        raise HTTPException(404, f"Unknown rule {rule_id}.")
    row = ensure_rules(db)[rule_id]
    row.enabled, row.severity, row.params = definition.default_enabled, definition.default_severity, dict(definition.default_params)
    row.updated_at, row.updated_by_name = utcnow(), user.full_name
    audit.record(db, user=user, action="rule.reset", entity_type="rule", entity_id=rule_id)
    db.commit()
    return row


# ------------------------------------------------------------------ snapshot
def _documents(db: Session, project_id: str) -> list[DocumentState]:
    docs = list(db.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.document_number)))
    revisions: dict[str, list[RevisionState]] = {}
    for r in db.scalars(select(DocumentRevision).join(Document).where(Document.project_id == project_id)):
        revisions.setdefault(r.document_id, []).append(RevisionState(r.revision_number, r.status.value, r.checksum, r.change_summary))
    return [DocumentState(d.id, d.document_number, d.name, d.discipline.value, d.status.value, d.author, d.source_system,
                          d.current_revision_number, tuple(sorted(revisions.get(d.id, []), key=lambda r: r.number)))
            for d in docs]


def _open_impacts(db: Session, project_id: str) -> list[OpenImpact]:
    analyses = {a.id: a for a in impact_service.latest_analyses(db, project_id)}
    if not analyses:
        return []
    dependencies = {d.id: d for d in db.scalars(select(Dependency).where(Dependency.project_id == project_id))}
    out = []
    for event in db.scalars(select(ImpactEvent).where(ImpactEvent.analysis_id.in_(list(analyses)))):
        analysis = analyses[event.analysis_id]
        if impact_service.event_state(event, analysis.changed_revision_number, dependencies) != "open":
            continue
        changed = db.get(Document, event.changed_document_id)
        out.append(OpenImpact(
            event_id=event.id, impacted_document_id=event.impacted_document_id,
            changed_document_number=changed.document_number, changed_revision_number=analysis.changed_revision_number,
            direct=event.direct, severity=event.severity, score=event.score,
            first_hop_number=event.path[0]["to_number"] if event.path else "",
            affected=tuple(AffectedRef(a["tag"], tuple(a["kinds"]), a["distance_mm"], tuple(a["reasons"]))
                           for a in event.affected_elements),
            affected_total=event.affected_element_count))
    return sorted(out, key=lambda i: i.event_id)


def _current_revision_id(db: Session, document: Document) -> str | None:
    if document.current_revision_number is None:
        return None
    return db.scalar(select(DocumentRevision.id).where(
        DocumentRevision.document_id == document.id, DocumentRevision.revision_number == document.current_revision_number,
        DocumentRevision.extraction_status == "ok", DocumentRevision.element_count <= MAX_ELEMENTS_PER_DOCUMENT))


def build_snapshot(db: Session, project_id: str, configs: dict[str, RuleConfig]) -> Snapshot:
    documents = _documents(db, project_id)
    dependencies = list(db.scalars(select(Dependency).where(Dependency.project_id == project_id)))
    edges = tuple(dependency_service.to_edge(d) for d in sorted(dependencies, key=lambda d: d.id))
    by_id = {d.id: d for d in db.scalars(select(Document).where(Document.project_id == project_id))}

    linked = {i for e in edges for i in (e.source, e.target)}
    references: dict[str, tuple[ElementReferences, ...]] = {}
    tags: dict[str, frozenset[str]] = {}
    if configs["UNRESOLVED_REFERENCE"].enabled:
        for doc_id in sorted(linked):
            revision_id = _current_revision_id(db, by_id[doc_id])
            if revision_id is None:
                continue
            found, names = [], set()
            for tag, props in db.execute(select(BimElement.tag, BimElement.properties).where(BimElement.revision_id == revision_id)):
                names.add(tag)
                raw = (props or {}).get("BasedOn")
                if raw:
                    found.append(ElementReferences(tag, tuple(str(r) for r in (raw if isinstance(raw, list) else [raw]))))
            tags[doc_id] = frozenset(names)
            if found:
                references[doc_id] = tuple(found)

    properties: dict[str, dict[str, dict]] = {}
    if configs["PARAMETER_MISMATCH"].enabled:
        wanted: dict[str, dict[str, set[str]]] = {}  # discipline -> tag -> properties
        for check in configs["PARAMETER_MISMATCH"].params.get("checks", []):
            for side in (check["left"], check["right"]):
                wanted.setdefault(side["discipline"], {}).setdefault(side["tag"], set()).add(side["property"])
        for document in by_id.values():
            tag_map = wanted.get(document.discipline.value)
            revision_id = _current_revision_id(db, document) if tag_map else None
            if revision_id is None:
                continue
            for row in db.scalars(select(BimElement).where(BimElement.revision_id == revision_id,
                                                           BimElement.tag.in_(list(tag_map)))):
                properties.setdefault(document.id, {})[row.tag] = {
                    p: (row.properties or {}).get(p) for p in tag_map[row.tag] if p in (row.properties or {})}

    return Snapshot(documents=tuple(documents), edges=edges, open_impacts=tuple(_open_impacts(db, project_id)),
                    references=references, tags=tags, properties=properties)


# ------------------------------------------------------------------ runs
def _persist_summary(run: ValidationRun, findings_view: list[tuple[str, str, bool]], configs: dict[str, RuleConfig],
                     documents_checked: int) -> None:
    """findings_view: (rule_id, severity, acknowledged) per issue."""
    class _F:  # minimal adapter so assess() can be reused for stored issues
        def __init__(self, rule_id, severity, fingerprint):
            self.rule_id, self.severity, self.fingerprint = rule_id, severity, fingerprint
    adapters = [_F(r, s, str(i)) for i, (r, s, _) in enumerate(findings_view)]
    acknowledged = {str(i) for i, (_, _, a) in enumerate(findings_view) if a}
    blocking = blocking_severity(configs)
    readiness = assess(adapters, acknowledged, blocking)  # type: ignore[arg-type]
    run.status = readiness.status
    run.summary = {
        "documents_checked": documents_checked, "total": len(findings_view), "open": readiness.open_count,
        "acknowledged": readiness.acknowledged_count, "blocking": readiness.blocking_count,
        "blocking_severity": blocking, "open_by_severity": readiness.open_by_severity, "by_rule": readiness.by_rule}


def run_validation(db: Session, project_id: str, user: User | None) -> ValidationRun:
    started = time.perf_counter()
    configs = rule_configs(db, project_id)
    snapshot = build_snapshot(db, project_id, configs)
    findings = run_rules(snapshot, configs)
    acknowledgements = {a.fingerprint: a for a in db.scalars(
        select(IssueAcknowledgement).where(IssueAcknowledgement.project_id == project_id))}

    run = ValidationRun(status="PENDING", 
        project_id=project_id, created_by_id=user.id if user else None, created_by_name=user.full_name if user else "system",
        rules_snapshot={rid: {"enabled": c.enabled, "severity": c.severity, "params": dict(c.params)} for rid, c in configs.items()})
    db.add(run)
    db.flush()
    view: list[tuple[str, str, bool]] = []
    for f in findings:
        ack = acknowledgements.get(f.fingerprint) if f.severity != "CRITICAL" else None
        db.add(ValidationIssue(
            run_id=run.id, project_id=project_id, rule_id=f.rule_id, severity=f.severity, document_id=f.document_id,
            document_number=f.document_number, element_tag=f.element_tag, title=f.title, message=f.message,
            recommended_action=f.recommended_action, details=dict(f.details), fingerprint=f.fingerprint,
            status="acknowledged" if ack else "open", acknowledged_by_name=ack.acknowledged_by_name if ack else "",
            acknowledged_at=ack.acknowledged_at if ack else None, acknowledgement_note=ack.note if ack else ""))
        view.append((f.rule_id, f.severity, ack is not None))
    _persist_summary(run, view, configs, len(snapshot.documents))
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    audit.record(db, user=user, action="validation.run", entity_type="project", entity_id=project_id, project_id=project_id,
                 detail={"status": run.status, "open": run.summary["open"], "blocking": run.summary["blocking"],
                         "acknowledged": run.summary["acknowledged"]})
    db.commit()
    return run


def refresh_run(db: Session, run: ValidationRun) -> None:
    """Recomputes a run's status from its issues after an acknowledgement changed."""
    configs = {rid: RuleConfig(rid, v["enabled"], v["severity"], v["params"]) for rid, v in run.rules_snapshot.items()}
    view = [(i.rule_id, i.severity, i.status == "acknowledged") for i in db.scalars(
        select(ValidationIssue).where(ValidationIssue.run_id == run.id))]
    _persist_summary(run, view, configs, run.summary.get("documents_checked", 0))


def acknowledge(db: Session, issue: ValidationIssue, user: User, note: str) -> ValidationIssue:
    if issue.severity == "CRITICAL":
        raise HTTPException(409, "Critical issues cannot be acknowledged. Resolve the cause and validate again.")
    if issue.status == "acknowledged":
        raise HTTPException(409, "This issue has already been acknowledged.")
    now = utcnow()
    issue.status, issue.acknowledged_by_name, issue.acknowledged_at, issue.acknowledgement_note = "acknowledged", user.full_name, now, note
    existing = db.scalar(select(IssueAcknowledgement).where(
        IssueAcknowledgement.project_id == issue.project_id, IssueAcknowledgement.fingerprint == issue.fingerprint))
    if existing is None:
        db.add(IssueAcknowledgement(project_id=issue.project_id, fingerprint=issue.fingerprint, rule_id=issue.rule_id, note=note,
                                    acknowledged_by_id=user.id, acknowledged_by_name=user.full_name, acknowledged_at=now))
    # the same finding in the run being looked at is the only one affected; later runs pick the acknowledgement up
    run = db.get(ValidationRun, issue.run_id)
    db.flush()
    refresh_run(db, run)
    audit.record(db, user=user, action="issue.acknowledged", entity_type="issue", entity_id=issue.id, project_id=issue.project_id,
                 detail={"rule": issue.rule_id, "document": issue.document_number, "severity": issue.severity, "note": note})
    db.commit()
    return issue


def revoke(db: Session, issue: ValidationIssue, user: User) -> ValidationIssue:
    if issue.status != "acknowledged":
        raise HTTPException(409, "This issue is not acknowledged.")
    issue.status, issue.acknowledged_by_name, issue.acknowledged_at, issue.acknowledgement_note = "open", "", None, ""
    for ack in db.scalars(select(IssueAcknowledgement).where(
            IssueAcknowledgement.project_id == issue.project_id, IssueAcknowledgement.fingerprint == issue.fingerprint)):
        db.delete(ack)
    db.flush()
    refresh_run(db, db.get(ValidationRun, issue.run_id))
    audit.record(db, user=user, action="issue.acknowledgement_revoked", entity_type="issue", entity_id=issue.id,
                 project_id=issue.project_id, detail={"rule": issue.rule_id, "document": issue.document_number})
    db.commit()
    return issue

