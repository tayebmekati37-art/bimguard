from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, page_params, require_roles
from app.api.projects import get_project_or_404
from app.core.clock import utcnow
from app.db.session import get_db
from app.engines.graph import Impacted
from app.models.dependency import Dependency
from app.models.document import Document
from app.models.project import ProjectStatus
from app.models.user import Role, User
from app.schemas.common import Page
from app.schemas.dependency import (
    DependencyCreate, DependencyOut, DependencyUpdate, GraphNode, GraphOut, ImpactItem, ImpactOut, PathStepOut,
    ValidateRequest,
)
from app.services import audit
from app.services import dependencies as service

router = APIRouter(tags=["dependencies"])
can_edit = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.ENGINEER)
can_validate = require_roles(Role.ADMIN, Role.BIM_COORDINATOR, Role.ENGINEER, Role.REVIEWER)


def _dependency_or_404(db: Session, dependency_id: str) -> Dependency:
    dependency = db.get(Dependency, dependency_id)
    if dependency is None:
        raise HTTPException(404, "Dependency not found. It may have been removed.")
    return dependency


def _out(db: Session, dependency: Dependency) -> DependencyOut:
    _, documents, _ = service.load_graph(db, dependency.project_id)
    return service.to_out(dependency, documents)


def _ensure_active(db: Session, dependency: Dependency) -> None:
    project = get_project_or_404(db, dependency.project_id)
    if project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(409, f"Project '{project.name}' is archived. Restore it before changing dependencies.")


@router.post("/dependencies", response_model=DependencyOut, status_code=201)
def create_dependency(body: DependencyCreate, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    return _out(db, service.create_dependency(db, user, body))


@router.get("/projects/{project_id}/dependencies", response_model=Page[DependencyOut])
def list_dependencies(
    project_id: str,
    document_id: str | None = None,
    relationship_type: str | None = Query(None, max_length=32),
    stale: bool | None = None,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> Page[DependencyOut]:
    get_project_or_404(db, project_id)
    _, documents, dependencies = service.load_graph(db, project_id)
    rows = [service.to_out(d, documents) for d in dependencies]
    if document_id:
        rows = [r for r in rows if document_id in (r.source_document_id, r.target_document_id)]
    if relationship_type:
        rows = [r for r in rows if r.relationship_type == relationship_type]
    if stale is not None:
        rows = [r for r in rows if r.is_stale == stale]
    rows.sort(key=lambda r: (r.source_number, r.target_number, r.relationship_type))
    return Page[DependencyOut](items=rows[page.offset:page.offset + page.limit], total=len(rows),
                               limit=page.limit, offset=page.offset)


@router.get("/dependencies/{dependency_id}", response_model=DependencyOut)
def get_dependency(dependency_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return _out(db, _dependency_or_404(db, dependency_id))


@router.patch("/dependencies/{dependency_id}", response_model=DependencyOut)
def update_dependency(dependency_id: str, body: DependencyUpdate, db: Session = Depends(get_db),
                      user: User = Depends(can_edit)):
    dependency = _dependency_or_404(db, dependency_id)
    _ensure_active(db, dependency)
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None and getattr(dependency, field) != value:
            changes[field] = {"old": getattr(dependency, field), "new": value}
            setattr(dependency, field, value)
    if changes:
        audit.record(db, user=user, action="dependency.updated", entity_type="dependency", entity_id=dependency.id,
                     project_id=dependency.project_id, detail=changes)
        db.commit()
    return _out(db, dependency)


@router.delete("/dependencies/{dependency_id}", status_code=204)
def delete_dependency(dependency_id: str, db: Session = Depends(get_db), user: User = Depends(can_edit)) -> None:
    dependency = _dependency_or_404(db, dependency_id)
    _ensure_active(db, dependency)
    _, documents, _ = service.load_graph(db, dependency.project_id)
    audit.record(db, user=user, action="dependency.deleted", entity_type="dependency", entity_id=dependency.id,
                 project_id=dependency.project_id,
                 detail={"source": documents[dependency.source_document_id].document_number,
                         "target": documents[dependency.target_document_id].document_number,
                         "type": dependency.relationship_type})
    db.delete(dependency)
    db.commit()


@router.post("/dependencies/{dependency_id}/validate", response_model=DependencyOut)
def validate_dependency(dependency_id: str, body: ValidateRequest | None = None, db: Session = Depends(get_db),
                        user: User = Depends(can_validate)):
    """Records that the dependent document has been reviewed against a revision of the document that supplies
    its information (default: that document's current revision). This is what clears a stale dependency."""
    dependency = _dependency_or_404(db, dependency_id)
    _ensure_active(db, dependency)
    edge = service.to_edge(dependency)
    if edge.provider is None:
        raise HTTPException(409, "Spatial relationships run both ways and have no single revision to validate against.")
    provider = db.get(Document, edge.provider)
    current = provider.current_revision_number
    if current is None:
        raise HTTPException(409, f"{provider.document_number} has no revisions yet, so there is nothing to validate against.")
    revision = body.revision_number if body and body.revision_number else current
    if revision > current:
        raise HTTPException(422, f"{provider.document_number} has no revision v{revision} (current is v{current}).")
    old = dependency.validated_against_revision
    dependency.validated_against_revision = revision
    dependency.validated_at = utcnow()
    dependency.validated_by_name = user.full_name
    audit.record(db, user=user, action="dependency.validated", entity_type="dependency", entity_id=dependency.id,
                 project_id=dependency.project_id,
                 detail={"provider": provider.document_number, "old_revision": old, "new_revision": revision})
    db.commit()
    return _out(db, dependency)


@router.get("/projects/{project_id}/graph", response_model=GraphOut)
def project_graph(project_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> GraphOut:
    get_project_or_404(db, project_id)
    graph, documents, dependencies = service.load_graph(db, project_id)
    edges = [service.to_out(d, documents) for d in dependencies]
    nodes = [GraphNode(id=d.id, document_number=d.document_number, name=d.name, discipline=d.discipline.value,
                       status=d.status.value, current_revision_number=d.current_revision_number)
             for d in sorted(documents.values(), key=lambda d: d.document_number)]
    cycles = sorted(sorted(documents[i].document_number for i in cycle) for cycle in graph.find_cycles())
    return GraphOut(nodes=nodes, edges=edges, cycles=cycles, stale_count=sum(1 for e in edges if e.is_stale))


@router.get("/documents/{document_id}/impact", response_model=ImpactOut)
def document_impact(
    document_id: str,
    direction: str = Query("downstream", pattern="^(downstream|upstream)$"),
    max_depth: int | None = Query(None, ge=1, le=50),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> ImpactOut:
    """downstream: documents a change to this one can reach. upstream: documents whose changes can reach this one."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found. It may have been deleted.")
    graph, documents, _ = service.load_graph(db, document.project_id)
    found: list[Impacted] = (graph.impact_from(document_id, max_depth) if direction == "downstream"
                             else graph.dependencies_of(document_id, max_depth))
    items = [ImpactItem(
        document_id=i.node, document_number=documents[i.node].document_number, name=documents[i.node].name,
        discipline=documents[i.node].discipline.value,
        current_revision_number=documents[i.node].current_revision_number, distance=i.distance, direct=i.direct,
        strength=i.strength,
        path=[PathStepOut(edge_id=s.edge_id, from_number=documents[s.from_node].document_number,
                          to_number=documents[s.to_node].document_number,
                          relationship_type=s.relationship_type.value, strength=s.strength, reason=s.reason)
              for s in i.path]) for i in found]
    items.sort(key=lambda i: (-i.strength, i.distance, i.document_number))
    return ImpactOut(root_document_id=document.id, root_document_number=document.document_number,
                     direction=direction, radius=max((i.distance for i in found), default=0), items=items)
