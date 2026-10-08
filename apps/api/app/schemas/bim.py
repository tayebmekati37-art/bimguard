from pydantic import BaseModel, ConfigDict


class ElementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision_id: str
    guid: str
    ifc_class: str
    name: str
    tag: str
    level: str | None
    room: str | None
    material: str | None
    properties: dict
    geometry: dict


class CountItem(BaseModel):
    key: str
    count: int


class ModelSummary(BaseModel):
    total: int
    by_class: list[CountItem]
    by_level: list[CountItem]
