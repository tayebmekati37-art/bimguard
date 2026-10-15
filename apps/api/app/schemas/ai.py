from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    ai_enabled: bool = False


class AskResponse(BaseModel):
    answer: str
    path: str
    question_type: str
    violations: list[str] = Field(default_factory=list)


class AiStatusResponse(BaseModel):
    enabled: bool
    model: str | None = None
    hourly_limit: int