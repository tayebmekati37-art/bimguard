from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    title: str
    body: str
    link: str
    project_id: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCountOut(BaseModel):
    count: int