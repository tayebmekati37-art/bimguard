from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import Role


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    expires_in: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str
    role: Role


class RefreshRequest(BaseModel):
    """Body for POST /auth/refresh and (optionally) POST /auth/logout."""
    refresh_token: str

class SessionOut(BaseModel):
    """One active session (refresh-token family) for the current user."""
    family_id: str
    started_at: datetime
    last_active_at: datetime
    expires_at: datetime
    rotation_count: int
    is_current: bool
