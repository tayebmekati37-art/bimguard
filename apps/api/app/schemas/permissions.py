from pydantic import BaseModel


class PermissionsOut(BaseModel):
    role: str
    capabilities: dict[str, bool]