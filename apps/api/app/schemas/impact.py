from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import Page


class ImpactEventOut(BaseModel):
    id: str
    analysis_id: str
    changed_document_id: str
    changed_document_number: str
    changed_revision_number: int
    impacted_document_id: str
    impacted_document_number: str
    impacted_name: str
    impacted_discipline: str
    impacted_status: str
    distance: int
    direct: bool
    score: float
    severity: str
    confidence: float
    state: str  # open | reviewed | advisory
    reason: str
    formula: str
    factors: list[dict]
    path: list[dict]
    affected_elements: list[dict]
    affected_element_count: int
    note: str
    first_edge_id: str | None
    dependency_validated_against: int | None
    validated_by_name: str
    validated_at: datetime | None
    created_at: datetime


class AnalysisOut(BaseModel):
    id: str
    changed_document_id: str
    changed_document_number: str
    changed_revision_number: int
    created_at: datetime
    summary: dict
    config: dict


class ImpactCounts(BaseModel):
    total: int
    open: int
    reviewed: int
    advisory: int
    open_by_severity: dict[str, int]


class ProjectImpactOut(BaseModel):
    analyses: list[AnalysisOut]
    counts: ImpactCounts
    events: Page[ImpactEventOut]
