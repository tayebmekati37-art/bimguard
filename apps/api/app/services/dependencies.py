from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.engines.graph import DependencyGraph, Edge, RelationshipType, is_stale
from app.models.dependency import Dependency
from app.models.document import Document
from app.models.user import User
from app.schemas.dependency import DependencyCreate, DependencyOut
from app.services import audit


def to_edge(dep: Dependency) -> Edge:
    return Edge(id=dep.id, source=dep.source_document_id, target=dep.target_document_id,
                relationship_type=RelationshipType(dep.relationship_type), confidence=dep.confidence,
                reason=dep.reason, validated_against_revision=dep.validated_against_revision)


def load_graph(db: Session, project_id: str) -> tuple[DependencyGraph, dict[str, Document], list[Dependency]]:
    documents = {d.id: d for d in db.scalars(select(Document).where(Document.project_id == project_id))}
    dependencies = list(db.scalars(select(Dependency).where(Dependency.project_id == project_id)
                                   .order_by(Dependency.created_at, Dependency.id)))
    graph = DependencyGraph(documents.keys(), [to_edge(d) for d in dependencies])
    return graph, documents, dependencies


def to_out(dep: Dependency, documents: dict[str, Document]) -> DependencyOut:
    edge = to_edge(dep)
    source, target = documents[dep.source_document_id], documents[dep.target_document_id]
    provider = documents.get(edge.provider) if edge.provider else None
    provider_revision = provider.current_revision_number if provider else None
    return DependencyOut(
        id=dep.id, project_id=dep.project_id,
        source_document_id=source.id, source_number=source.document_number, source_name=source.name,
        target_document_id=target.id, target_number=target.document_number, target_name=target.name,
        relationship_type=dep.relationship_type, flow=edge.flow.value,
        provider_document_id=provider.id if provider else None,
        provider_number=provider.document_number if provider else None,
        provider_current_revision=provider_revision, confidence=dep.confidence, strength=edge.strength(),
        reason=dep.reason, validated_against_revision=dep.validated_against_revision,
        validated_at=dep.validated_at, validated_by_name=dep.validated_by_name,
        is_stale=is_stale(edge, provider_revision), created_by_name=dep.created_by_name, created_at=dep.created_at,
    )


def create_dependency(db: Session, user: User, body: DependencyCreate) -> Dependency:
    if body.source_document_id == body.target_document_id:
        raise HTTPException(422, "A document cannot depend on itself.")
    source, target = db.get(Document, body.source_document_id), db.get(Document, body.target_document_id)
    if source is None or target is None:
        raise HTTPException(404, "One of the documents does not exist.")
    if source.project_id != target.project_id:
        raise HTTPException(422, "Both documents must belong to the same project.")
    if source.project.status.value == "archived":
        raise HTTPException(409, f"Project '{source.project.name}' is archived. Restore it before changing dependencies.")
    kind = RelationshipType(body.relationship_type)
    duplicate = db.scalar(select(Dependency).where(
        Dependency.source_document_id == source.id, Dependency.target_document_id == target.id,
        Dependency.relationship_type == kind.value))
    if duplicate is not None:
        raise HTTPException(409, f"{source.document_number} already has a '{kind.value}' relationship with "
                                 f"{target.document_number}.")

    edge = Edge(id="new", source=source.id, target=target.id, relationship_type=kind)
    provider = {source.id: source, target.id: target}.get(edge.provider) if edge.provider else None
    validated = body.validated_against_revision
    if validated is None and provider is not None:
        validated = provider.current_revision_number  # registered as consistent with the current state
    if validated is not None and provider is not None and provider.current_revision_number is not None \
            and validated > provider.current_revision_number:
        raise HTTPException(422, f"{provider.document_number} has no revision v{validated} yet "
                                 f"(current is v{provider.current_revision_number}).")

    dependency = Dependency(
        project_id=source.project_id, source_document_id=source.id, target_document_id=target.id,
        relationship_type=kind.value, confidence=body.confidence, reason=body.reason,
        validated_against_revision=validated, validated_at=utcnow() if validated is not None else None,
        validated_by_name=user.full_name if validated is not None else "",
        created_by_id=user.id, created_by_name=user.full_name)
    db.add(dependency)
    db.flush()
    audit.record(db, user=user, action="dependency.created", entity_type="dependency", entity_id=dependency.id,
                 project_id=source.project_id,
                 detail={"source": source.document_number, "target": target.document_number,
                         "type": kind.value, "confidence": body.confidence})
    db.commit()
    return dependency
