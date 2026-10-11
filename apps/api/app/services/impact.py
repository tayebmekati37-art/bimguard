import logging
from dataclasses import asdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.bim.types import ElementData
from app.engines.impact import (
    DEFAULT_IMPACT_CONFIG, ChangedElement, ChangeInput, DocumentInfo, ImpactConfig, analyze_impact,
)
from app.models.bim import BimElement
from app.models.comparison import DetectedChange, RevisionComparison
from app.models.dependency import Dependency
from app.models.document import Document, DocumentRevision
from app.models.impact import ImpactAnalysis, ImpactEvent
from app.models.user import User
from app.services import audit
from app.services import dependencies as dependency_service

log = logging.getLogger("bimguard.impact")
CHUNK = 500
_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _info(document: Document) -> DocumentInfo:
    return DocumentInfo(id=document.id, number=document.document_number, discipline=document.discipline.value,
                        status=document.status.value, current_revision_number=document.current_revision_number)


def _to_data(row: BimElement) -> ElementData:
    return ElementData(guid=row.guid, ifc_class=row.ifc_class, name=row.name, tag=row.tag, level=row.level,
                       room=row.room, material=row.material, properties=row.properties or {},
                       geometry=row.geometry or {})


def _rows_by_guid(db: Session, revision_id: str, guids: set[str]) -> dict[str, BimElement]:
    out: dict[str, BimElement] = {}
    wanted = sorted(guids)
    for i in range(0, len(wanted), CHUNK):
        for row in db.scalars(select(BimElement).where(BimElement.revision_id == revision_id,
                                                       BimElement.guid.in_(wanted[i:i + CHUNK]))):
            out[row.guid] = row
    return out


def _changed_elements(db: Session, comparison: RevisionComparison, rows: list[DetectedChange]) -> list[ChangedElement]:
    groups: dict[str, list[DetectedChange]] = {}
    for row in rows:
        if row.element_guid:
            groups.setdefault(row.element_guid, []).append(row)
    old_guids = {g: next((r.detail.get("old_guid") for r in rs if r.detail.get("old_guid")), g)
                 for g, rs in groups.items()}
    old_rows = _rows_by_guid(db, comparison.from_revision_id, set(old_guids.values()))
    new_rows = _rows_by_guid(db, comparison.to_revision_id, set(groups))
    changed: list[ChangedElement] = []
    for guid, rs in sorted(groups.items(), key=lambda kv: (kv[1][0].element_tag, kv[0])):
        old, new = old_rows.get(old_guids[guid]), new_rows.get(guid)
        lead = max(rs, key=lambda r: (_SEVERITY_RANK.get(r.severity, 0), r.summary))
        rooms: set[str] = {x.room for x in (old, new) if x is not None and x.room}
        for r in rs:
            if r.field == "room":
                rooms |= {str(v) for v in (r.old_value, r.new_value) if v}
        element = new or old
        if element is not None and element.ifc_class == "IfcSpace" and element.tag:
            rooms.add(element.tag)
        changed.append(ChangedElement(
            guid=guid, tag=lead.element_tag, ifc_class=lead.ifc_class,
            change_types=tuple(sorted({r.change_type for r in rs})), summary=lead.summary,
            rooms=frozenset(rooms), level=element.level if element is not None else None,
            old_geometry=old.geometry if old is not None else None,
            new_geometry=new.geometry if new is not None else None))
    return changed


def _load_dependents(db: Session, doc_ids: list[str], documents: dict[str, Document],
                     config: ImpactConfig) -> tuple[dict[str, list[ElementData]], dict[str, str]]:
    elements: dict[str, list[ElementData]] = {}
    notes: dict[str, str] = {}
    for doc_id in doc_ids:
        document = documents[doc_id]
        if document.current_revision_number is None:
            notes[doc_id] = "Element-level analysis unavailable: the document has no revisions."
            continue
        revision = db.scalar(select(DocumentRevision).where(
            DocumentRevision.document_id == doc_id, DocumentRevision.revision_number == document.current_revision_number))
        if revision is None or revision.extraction_status != "ok":
            notes[doc_id] = "Element-level analysis unavailable: the current revision has no readable model data."
        elif (revision.element_count or 0) > config.max_elements_for_element_analysis:
            notes[doc_id] = (f"Element-level analysis skipped: the model has {revision.element_count} elements "
                             f"(limit {config.max_elements_for_element_analysis}).")
        else:
            elements[doc_id] = [_to_data(r) for r in db.scalars(
                select(BimElement).where(BimElement.revision_id == revision.id))]
    return elements, notes


def analyze_comparison(db: Session, comparison: RevisionComparison, user: User | None = None,
                       config: ImpactConfig = DEFAULT_IMPACT_CONFIG) -> ImpactAnalysis:
    new_revision = db.get(DocumentRevision, comparison.to_revision_id)
    document = new_revision.document
    graph, documents, _ = dependency_service.load_graph(db, document.project_id)
    rows = list(db.scalars(select(DetectedChange).where(DetectedChange.comparison_id == comparison.id)))
    changes = [ChangeInput(r.change_type, r.severity, r.confidence, r.ifc_class, r.element_tag, r.summary) for r in rows]

    db.execute(delete(ImpactAnalysis).where(ImpactAnalysis.comparison_id == comparison.id))
    analysis = ImpactAnalysis(
        project_id=document.project_id, comparison_id=comparison.id, changed_document_id=document.id,
        changed_revision_id=new_revision.id, changed_revision_number=new_revision.revision_number,
        config=config.to_dict())
    db.add(analysis)
    db.flush()

    results = []
    if changes:
        reachable = [i.node for i in graph.impact_from(document.id)]
        dependents, notes = _load_dependents(db, reachable, documents, config)
        results = analyze_impact(
            graph=graph, root=_info(document), root_revision=new_revision.revision_number,
            root_status=new_revision.status.value, documents={k: _info(v) for k, v in documents.items()},
            changes=changes, changed_elements=_changed_elements(db, comparison, rows),
            dependent_elements=dependents, element_notes=notes, config=config)

    numbers = {k: v.document_number for k, v in documents.items()}
    for r in results:
        db.add(ImpactEvent(
            analysis_id=analysis.id, project_id=document.project_id, changed_document_id=document.id,
            impacted_document_id=r.document_id, distance=r.distance, direct=r.direct, score=r.score,
            severity=r.severity.value, confidence=r.confidence, first_edge_id=r.first_edge_id, reason=r.reason,
            formula=r.formula, factors=[asdict(f) for f in r.factors],
            path=[{"edge_id": s.edge_id, "from_number": numbers[s.from_node], "to_number": numbers[s.to_node],
                   "relationship_type": s.relationship_type.value, "strength": s.strength,
                   "confidence": s.confidence, "reason": s.reason} for s in r.path],
            affected_elements=[{**asdict(a), "kinds": list(a.kinds), "reasons": list(a.reasons)}
                               for a in r.affected_elements],
            affected_element_count=r.affected_element_count, note=r.note))
    by_severity: dict[str, int] = {}
    for r in results:
        by_severity[r.severity.value] = by_severity.get(r.severity.value, 0) + 1
    analysis.summary = {"total": len(results), "by_severity": by_severity, "changes": len(changes),
                        "radius": max((r.distance for r in results), default=0)}
    audit.record(db, user=user, action="impact.analyzed", entity_type="revision", entity_id=new_revision.id,
                 project_id=document.project_id,
                 detail={"document_number": document.document_number, "revision": new_revision.revision_number,
                         **analysis.summary})
    db.commit()
    return analysis


def safe_analyze(db: Session, comparison: RevisionComparison, user: User | None = None) -> None:
    """Impact analysis must never break the operation that triggered it."""
    try:
        analyze_comparison(db, comparison, user)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Impact analysis failed for comparison %s", comparison.id)


def latest_analyses(db: Session, project_id: str) -> list[ImpactAnalysis]:
    """The newest analysis for each changed document: older revisions' impacts are superseded."""
    best: dict[str, ImpactAnalysis] = {}
    for analysis in db.scalars(select(ImpactAnalysis).where(ImpactAnalysis.project_id == project_id)):
        current = best.get(analysis.changed_document_id)
        if current is None or (analysis.changed_revision_number, analysis.created_at) > \
                (current.changed_revision_number, current.created_at):
            best[analysis.changed_document_id] = analysis
    return sorted(best.values(), key=lambda a: a.created_at, reverse=True)


def reanalyze_project(db: Session, project_id: str, user: User | None = None) -> int:
    """Re-runs the analysis for each document's latest comparison, for example after the graph changed."""
    doc_ids = list(db.scalars(select(Document.id).where(Document.project_id == project_id)))
    latest: dict[str, tuple[int, RevisionComparison]] = {}
    for comparison, number in db.execute(
            select(RevisionComparison, DocumentRevision.revision_number)
            .join(DocumentRevision, DocumentRevision.id == RevisionComparison.to_revision_id)
            .where(RevisionComparison.document_id.in_(doc_ids))):
        if comparison.document_id not in latest or number > latest[comparison.document_id][0]:
            latest[comparison.document_id] = (number, comparison)
    for _, comparison in latest.values():
        analyze_comparison(db, comparison, user)
    return len(latest)


def safe_reanalyze(db: Session, project_id: str, user: User | None = None) -> None:
    try:
        reanalyze_project(db, project_id, user)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Impact re-analysis failed for project %s", project_id)


def event_state(event: ImpactEvent, changed_revision_number: int, dependencies: dict[str, Dependency]) -> str:
    """open: the first dependency on the path has not been reviewed against the changed revision.
    reviewed: it has. advisory: the path starts with a two-way relationship, which cannot be reviewed.
    Indirect impacts follow their first hop: once that document is reviewed, the rest is its own revision cycle."""
    dependency = dependencies.get(event.first_edge_id or "")
    if dependency is None:
        return "advisory"
    edge = dependency_service.to_edge(dependency)
    if edge.provider is None:
        return "advisory"
    validated = dependency.validated_against_revision
    return "reviewed" if validated is not None and validated >= changed_revision_number else "open"


def first_hop_dependency(event: ImpactEvent, dependencies: dict[str, Dependency]) -> Dependency | None:
    return dependencies.get(event.first_edge_id or "")

