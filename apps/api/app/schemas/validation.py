from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RuleOut(BaseModel):
    rule_id: str
    name: str
    description: str
    category: str
    enabled: bool
    severity: str
    params: dict
    default_enabled: bool
    default_severity: str
    default_params: dict
    is_default: bool
    configurable_severity: bool
    can_disable: bool
    updated_at: datetime
    updated_by_name: str


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    severity: str | None = None
    params: dict | None = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    created_at: datetime
    created_by_name: str
    status: str
    summary: dict
    rules_snapshot: dict
    duration_ms: int


class IssueOut(BaseModel):
    id: str
    run_id: str
    rule_id: str
    rule_name: str
    category: str
    severity: str
    document_id: str | None
    document_number: str
    element_tag: str
    title: str
    message: str
    recommended_action: str
    details: dict
    status: str
    acknowledged_by_name: str
    acknowledged_at: datetime | None
    acknowledgement_note: str


class AcknowledgeRequest(BaseModel):
    note: str = Field(min_length=5, max_length=2000)
