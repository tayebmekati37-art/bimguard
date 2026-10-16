from datetime import datetime

from pydantic import BaseModel


class ProfileRuleOut(BaseModel):
    enabled: bool | None = None
    severity: str | None = None
    params: dict | None = None


class ProfileOut(BaseModel):
    schema_version: int
    id: str
    name: str
    description: str
    illustrative: bool
    rules: dict[str, ProfileRuleOut]


class ProfileSummaryOut(BaseModel):
    schema_version: int
    id: str
    name: str
    description: str
    illustrative: bool
    rule_count: int


class ActivationOut(BaseModel):
    project_id: str
    profile_id: str | None
    activated_at: datetime | None
    activated_by_name: str | None


class ActivateRequest(BaseModel):
    profile_id: str