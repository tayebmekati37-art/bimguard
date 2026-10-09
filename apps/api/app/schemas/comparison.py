from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    element_guid: str | None
    element_tag: str
    element_name: str
    ifc_class: str
    change_type: str
    field: str
    old_value: Any
    new_value: Any
    severity: str
    confidence: float
    summary: str
    match_method: str
    detail: dict


class ComparisonOut(BaseModel):
    id: str
    project_id: str
    document_id: str
    document_number: str
    from_revision_id: str
    to_revision_id: str
    from_revision_number: int
    to_revision_number: int
    created_at: datetime
    created_by_name: str
    total_changes: int
    counts: dict
    config: dict


class CompareRequest(BaseModel):
    against_revision_id: str | None = None


class PlanElement(BaseModel):
    guid: str
    tag: str
    name: str
    ifc_class: str
    status: str  # added | removed | modified | unchanged
    change_types: list[str]
    old: dict | None
    new: dict | None


class PlanOut(BaseModel):
    changed: list[PlanElement]
    context: list[PlanElement]
