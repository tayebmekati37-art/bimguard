"""Deterministic answer templates.

Builds a plain-English answer from facts alone. No AI, no network.
The output is what the user sees when AI is off, or when a grounding
check rejects a model reply.
"""
from __future__ import annotations

from app.ai.facts import Fact
from app.ai.router import QuestionType


def _bullet(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _facts_of_kind(facts: list[Fact], *kinds: str) -> list[Fact]:
    wanted = set(kinds)
    return [f for f in facts if f.kind in wanted]


def _render_affected_by(facts: list[Fact], ctx: dict) -> str:
    doc = ctx.get("document_number") or ctx.get("doc") or "the document"
    related = _facts_of_kind(facts, "dependency", "impact")
    if not related:
        return f"No documents are affected by {doc}."
    lines = [f.text for f in related]
    return f"Documents affected by {doc}:\n{_bullet(lines)}"


def _render_affects(facts: list[Fact], ctx: dict) -> str:
    doc = ctx.get("document_number") or ctx.get("doc") or "the document"
    related = _facts_of_kind(facts, "dependency", "impact")
    if not related:
        return f"{doc} does not affect any other documents."
    lines = [f.text for f in related]
    return f"Documents affected by {doc}:\n{_bullet(lines)}"


def _render_status(facts: list[Fact], ctx: dict) -> str:
    doc = ctx.get("document_number") or ctx.get("doc") or "the document"
    status = _facts_of_kind(facts, "change", "validation")
    if not status:
        return f"No status information available for {doc}."
    lines = [f.text for f in status]
    return f"Status of {doc}:\n{_bullet(lines)}"


def _render_validation(facts: list[Fact], ctx: dict) -> str:
    doc = ctx.get("document_number") or ctx.get("doc")
    issues = _facts_of_kind(facts, "validation")
    if not issues:
        subject = f" for {doc}" if doc else ""
        return f"No validation issues found{subject}."
    lines = [f.text for f in issues]
    header = f"Validation issues for {doc}:" if doc else "Validation issues:"
    return f"{header}\n{_bullet(lines)}"


def _render_dependencies(facts: list[Fact], ctx: dict) -> str:
    doc = ctx.get("document_number") or ctx.get("doc") or "the document"
    deps = _facts_of_kind(facts, "dependency")
    if not deps:
        return f"No dependencies recorded for {doc}."
    lines = [f.text for f in deps]
    return f"Dependencies for {doc}:\n{_bullet(lines)}"


def _render_summary(facts: list[Fact], ctx: dict) -> str:
    doc = ctx.get("document_number") or ctx.get("doc")
    if not facts:
        subject = f" for {doc}" if doc else ""
        return f"No information available{subject}."
    by_kind: dict[str, list[str]] = {}
    for f in facts:
        by_kind.setdefault(f.kind, []).append(f.text)
    header = f"Summary for {doc}:" if doc else "Summary:"
    lines = [f"{kind}: {text}" for kind, texts in by_kind.items() for text in texts]
    return f"{header}\n{_bullet(lines)}"


def _render_unknown(facts: list[Fact], ctx: dict) -> str:
    return (
        "I can answer questions about affected-by, affects, status, "
        "validation, dependencies, and summaries. Please rephrase."
    )


_RENDERERS = {
    QuestionType.AFFECTED_BY: _render_affected_by,
    QuestionType.AFFECTS: _render_affects,
    QuestionType.STATUS: _render_status,
    QuestionType.VALIDATION: _render_validation,
    QuestionType.DEPENDENCIES: _render_dependencies,
    QuestionType.SUMMARY: _render_summary,
    QuestionType.UNKNOWN: _render_unknown,
}


def render(qtype: QuestionType, facts: list[Fact], context: dict | None = None) -> str:
    """Render a deterministic answer for the given question type."""
    ctx = context or {}
    renderer = _RENDERERS.get(qtype, _render_unknown)
    return renderer(facts, ctx)