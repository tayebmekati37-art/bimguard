from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.engines.graph import RelationshipType


class DependencyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    source_document_id: str
    target_document_id: str
    relationship_type: RelationshipType
    confidence: float = Field(default=1.0, gt=0, le=1)
    reason: str = Field(min_length=3, max_length=2000)
    validated_against_revision: int | None = Field(default=None, ge=1)


class DependencyUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    confidence: float | None = Field(default=None, gt=0, le=1)
    reason: str | None = Field(default=None, min_length=3, max_length=2000)


class ValidateRequest(BaseModel):
    revision_number: int | None = Field(default=None, ge=1)


class DependencyOut(BaseModel):
    id: str
    project_id: str
    source_document_id: str
    source_number: str
    source_name: str
    target_document_id: str
    target_number: str
    target_name: str
    relationship_type: str
    flow: str
    provider_document_id: str | None
    provider_number: str | None
    provider_current_revision: int | None
    confidence: float
    strength: float
    reason: str
    validated_against_revision: int | None
    validated_at: datetime | None
    validated_by_name: str
    is_stale: bool
    created_by_name: str
    created_at: datetime


class GraphNode(BaseModel):
    id: str
    document_number: str
    name: str
    discipline: str
    status: str
    current_revision_number: int | None
    health: str = "healthy"
    health_reasons: list[str] = []


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[DependencyOut]
    cycles: list[list[str]]  # document numbers
    stale_count: int


class PathStepOut(BaseModel):
    edge_id: str
    from_number: str
    to_number: str
    relationship_type: str
    strength: float
    reason: str


class ImpactItem(BaseModel):
    document_id: str
    document_number: str
    name: str
    discipline: str
    current_revision_number: int | None
    distance: int
    direct: bool
    strength: float
    path: list[PathStepOut]


class ImpactOut(BaseModel):
    root_document_id: str
    root_document_number: str
    direction: str
    radius: int
    items: list[ImpactItem]
