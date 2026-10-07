from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import Discipline, RevisionStatus


class DocumentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    document_number: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=255)
    discipline: Discipline
    author: str = Field(default="", max_length=120)
    source_system: str = Field(default="BIMGuard upload", max_length=80)
    metadata: dict = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    discipline: Discipline | None = None
    author: str | None = Field(default=None, max_length=120)
    source_system: str | None = Field(default=None, max_length=80)
    metadata: dict | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: str
    project_id: str
    document_number: str
    name: str
    discipline: Discipline
    file_type: str
    status: RevisionStatus
    current_revision_number: int | None
    author: str
    source_system: str
    metadata: dict = Field(default_factory=dict, validation_alias="meta")
    checksum: str
    issue_date: datetime | None
    created_at: datetime
    modified_at: datetime


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    revision_number: int
    original_filename: str
    file_size: int
    checksum: str
    uploaded_at: datetime
    created_by_name: str
    status: RevisionStatus
    change_summary: str
    previous_revision_id: str | None


class RevisionStatusUpdate(BaseModel):
    status: RevisionStatus


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    project_id: str | None
    user_email: str
    action: str
    entity_type: str
    entity_id: str | None
    detail: dict
