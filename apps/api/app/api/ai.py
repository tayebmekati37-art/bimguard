import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.orchestrator import Orchestrator
from app.ai.provider import AIProvider, OpenAICompatibleProvider
from app.api.deps import get_current_user
from app.api.projects import get_project_or_404
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import AiStatusResponse, AskRequest, AskResponse

router = APIRouter(tags=["ai"])

AI_HOURLY_LIMIT = 30


def get_ai_provider() -> AIProvider | None:
    """Return an OpenAI-compatible provider if configured, else None.

    Tests override this dependency to inject a ScriptedProvider.
    """
    if os.environ.get("AI_BASE_URL") and os.environ.get("AI_MODEL"):
        return OpenAICompatibleProvider()
    return None


@router.post("/projects/{project_id}/ask", response_model=AskResponse)
async def ask_project_question(
    project_id: str,
    body: AskRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    provider: AIProvider | None = Depends(get_ai_provider),
) -> AskResponse:
    """Answer a question about the project. AI is optional; templates always work."""
    get_project_or_404(db, project_id)
    orch = Orchestrator(db, provider=provider, hourly_limit=AI_HOURLY_LIMIT)
    result = await orch.answer(project_id, body.question, ai_enabled=body.ai_enabled)
    return AskResponse(
        answer=result.answer,
        path=result.path,
        question_type=result.question_type,
        violations=result.violations,
    )


@router.get("/ai/status", response_model=AiStatusResponse)
def ai_status(provider: AIProvider | None = Depends(get_ai_provider)) -> AiStatusResponse:
    """Report whether the AI layer is configured on the server."""
    enabled = provider is not None
    model = os.environ.get("AI_MODEL") if enabled else None
    return AiStatusResponse(enabled=enabled, model=model, hourly_limit=AI_HOURLY_LIMIT)