from pydantic import BaseModel, Field


class RoundTripReportOut(BaseModel):
    revision_id: str
    element_count: int
    matches: int
    missing: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)
    mismatches: list[dict] = Field(default_factory=list)
    ok: bool


class SourceVerificationReportOut(BaseModel):
    revision_id: str
    source_format: str
    ok: bool
    reason: str = ""
    parsed_element_count: int
    stored_element_count: int
    missing: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)