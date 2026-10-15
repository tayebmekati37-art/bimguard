from pydantic import BaseModel


class ReportProject(BaseModel):
    id: str
    name: str
    client: str
    status: str


class ReportIssueCounts(BaseModel):
    total: int
    open: int
    acknowledged: int


class ReportSummary(BaseModel):
    readiness_status: str
    documents: int
    documents_with_revision: int
    disciplines: dict
    dependencies: int
    stale_dependencies: int
    open_impacts: dict
    document_health: dict
    issue_counts: ReportIssueCounts


class ReadinessReportOut(BaseModel):
    """Shape of the JSON report. CSV and PDF are separate serializations."""
    generated_at: str
    schema_version: int
    project: ReportProject
    summary: ReportSummary
    validation: dict | None
    issues: list[dict]
    documents: list[dict]