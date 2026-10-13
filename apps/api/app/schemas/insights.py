from datetime import datetime

from pydantic import BaseModel


class DocHealthOut(BaseModel):
    document_id: str
    document_number: str
    name: str
    state: str
    reasons: list[str]


class ActivityOut(BaseModel):
    at: datetime
    user: str
    action: str
    text: str


class ValidationHealth(BaseModel):
    run_id: str
    status: str
    created_at: datetime
    open: int
    blocking: int
    acknowledged: int
    open_by_severity: dict[str, int]
    outdated: bool


class ProjectHealthOut(BaseModel):
    project_id: str
    project_name: str
    project_status: str
    client: str
    documents: int
    documents_with_revision: int
    disciplines: dict[str, int]
    dependencies: int
    stale_dependencies: int
    open_impacts: dict
    document_health: dict[str, int]
    documents_health: list[DocHealthOut]
    validation: ValidationHealth | None
    recent_activity: list[ActivityOut]
    last_change_at: datetime | None


class DashboardProject(BaseModel):
    project_id: str
    project_name: str
    client: str
    project_status: str
    documents: int
    stale_dependencies: int
    open_impacts: dict
    document_health: dict[str, int]
    validation: ValidationHealth | None
    last_change_at: datetime | None


class DashboardOut(BaseModel):
    totals: dict
    projects: list[DashboardProject]


class SearchHit(BaseModel):
    kind: str          # project | document | element | issue
    id: str
    title: str
    subtitle: str
    project_id: str
    project_name: str
    document_number: str = ""


class SearchOut(BaseModel):
    query: str
    projects: list[SearchHit]
    documents: list[SearchHit]
    elements: list[SearchHit]
    issues: list[SearchHit]


class OverviewDocument(BaseModel):
    id: str
    project_id: str
    document_number: str
    name: str
    discipline: str
    status: str
    current_revision_number: int | None
    author: str
    file_type: str
    modified_at: datetime


class OverviewLink(BaseModel):
    document_id: str
    document_number: str
    relationship_type: str
    current_revision: int | None
    validated_against_revision: int | None
    stale: bool


class OverviewComparison(BaseModel):
    id: str
    revision_id: str
    from_revision_number: int
    to_revision_number: int
    total_changes: int
    by_severity: dict[str, int]
    by_type: dict[str, int]


class OverviewImpact(BaseModel):
    changed_document_number: str
    changed_revision_number: int
    score: float
    severity: str
    direct: bool


class DocumentOverview(BaseModel):
    document: OverviewDocument
    health_state: str
    health_reasons: list[str]
    providers: list[OverviewLink]     # documents it relies on (direct)
    dependents: list[OverviewLink]    # documents that rely on it (direct)
    downstream_count: int
    radius: int
    latest_comparison: OverviewComparison | None
    open_impacts: list[OverviewImpact]
