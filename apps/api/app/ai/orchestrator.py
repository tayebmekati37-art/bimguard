"""Orchestrator for the AI explanation layer.

Ties together: router -> retrieval -> templates -> (optional) provider
-> grounding check -> AIQuery logging. AI is never required: every path
falls back to the deterministic template.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import retrieval, templates
from app.ai.facts import Fact
from app.ai.grounding import check as grounding_check
from app.ai.provider import AIProvider, AIProviderError
from app.ai.router import QuestionType, Router
from app.core.clock import utcnow
from app.models.ai_query import AIQuery

log = logging.getLogger("bimguard.ai.orchestrator")

_DOC_NUMBER_RE = re.compile(r"\b[A-Za-z]{1,6}-\d{1,4}\b")

SYSTEM_PROMPT = (
    "You reword the facts provided. Never add facts. "
    "Never invent document numbers, element tags, revisions, or links. "
    "Use only identifiers that appear in the facts."
)


@dataclass
class AIAnswer:
    answer: str
    path: str
    question_type: str
    facts: list[Fact] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    model_name: str | None = None


class Orchestrator:
    def __init__(self, db: Session, provider: AIProvider | None = None, hourly_limit: int = 30) -> None:
        self.db = db
        self.provider = provider
        self.hourly_limit = hourly_limit

    def _extract_document_number(self, question: str) -> str | None:
        m = _DOC_NUMBER_RE.search(question)
        return m.group(0).upper() if m else None

    def _recent_ai_count(self, project_id: str) -> int:
        since = utcnow() - timedelta(hours=1)
        stmt = select(func.count(AIQuery.id)).where(
            AIQuery.project_id == project_id,
            AIQuery.path == "ai",
            AIQuery.created_at >= since,
        )
        return int(self.db.scalar(stmt) or 0)

    def _log_row(
        self,
        project_id: str,
        question: str,
        qtype: QuestionType,
        answer: str,
        path: str,
        facts: list[Fact],
        violations: list[str],
        model_name: str | None,
    ) -> None:
        row = AIQuery(
            project_id=project_id,
            question=question,
            question_type=qtype.value,
            answer=answer,
            path=path,
            facts=[{"text": f.text, "kind": f.kind, "identifiers": list(f.identifiers)} for f in facts],
            violations=list(violations),
            model_name=model_name,
        )
        self.db.add(row)
        self.db.commit()

    def _template_answer(
        self,
        project_id: str,
        question: str,
        qtype: QuestionType,
        facts: list[Fact],
        ctx: dict,
        violations: list[str] | None = None,
    ) -> AIAnswer:
        text = templates.render(qtype, facts, ctx)
        violations = violations or []
        self._log_row(project_id, question, qtype, text, "template", facts, violations, None)
        return AIAnswer(
            answer=text, path="template", question_type=qtype.value,
            facts=facts, violations=violations, model_name=None,
        )

    async def answer(self, project_id: str, question: str, ai_enabled: bool = False) -> AIAnswer:
        qtype = Router().route(question)
        doc_number = self._extract_document_number(question)

        facts = retrieval.build_facts_for_project(self.db, project_id, qtype, doc_number)
        ctx: dict = {"document_number": doc_number} if doc_number else {}

        if not ai_enabled or self.provider is None:
            log.info("path=template reason=ai_off project=%s qtype=%s facts=%d",
                     project_id, qtype.value, len(facts))
            return self._template_answer(project_id, question, qtype, facts, ctx)

        if self._recent_ai_count(project_id) >= self.hourly_limit:
            log.info("path=template reason=limit project=%s count>=%d",
                     project_id, self.hourly_limit)
            return self._template_answer(project_id, question, qtype, facts, ctx)

        facts_text = "\n".join(f"- {f.text}" for f in facts) or "- (no facts)"
        user_prompt = f"Facts:\n{facts_text}\n\nQuestion: {question}"

        try:
            reply = await self.provider.complete(SYSTEM_PROMPT, user_prompt)
        except AIProviderError as e:
            log.warning("path=template reason=provider_error project=%s err=%s", project_id, e)
            return self._template_answer(project_id, question, qtype, facts, ctx)

        g = grounding_check(reply, facts)
        if not g.ok:
            log.info("path=template reason=grounding project=%s violations=%d",
                     project_id, len(g.violations))
            return self._template_answer(project_id, question, qtype, facts, ctx, g.violations)

        model_name = getattr(self.provider, "_model", None) or None
        self._log_row(project_id, question, qtype, reply, "ai", facts, [], model_name)
        log.info("path=ai project=%s qtype=%s facts=%d model=%s",
                 project_id, qtype.value, len(facts), model_name)
        return AIAnswer(
            answer=reply, path="ai", question_type=qtype.value,
            facts=facts, violations=[], model_name=model_name,
        )