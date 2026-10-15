"""Database -> facts for the AI explanation layer.

This is the only module under app/ai that touches the database. It reads
rows for one project and hands them to FactBuilder. No AI, no templates.

Sync Session, SQLAlchemy 2.x, mirrors app.services.impact style.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.facts import Fact, FactBuilder
from app.ai.router import QuestionType
from app.models.dependency import Dependency
from app.models.document import Document
from app.models.impact import ImpactEvent
from app.models.validation import ValidationIssue

log = logging.getLogger("bimguard.ai.retrieval")


def _doc_numbers(db: Session, doc_ids: set[str]) -> dict[str, str]:
    if not doc_ids:
        return {}
    rows = db.scalars(select(Document).where(Document.id.in_(list(doc_ids))))
    return {d.id: d.document_number for d in rows}


def _doc_id_for_number(db: Session, project_id: str, number: str | None) -> str | None:
    if not number:
        return None
    row = db.scalar(
        select(Document).where(
            Document.project_id == project_id,
            Document.document_number == number,
        )
    )
    return row.id if row else None


def build_facts_for_project(
    db: Session,
    project_id: str,
    question_type: QuestionType = QuestionType.SUMMARY,
    document_number: str | None = None,
) -> list[Fact]:
    """Read rows relevant to the project (and optional document) and return Facts.

    question_type is accepted for future narrowing but currently all four
    fact kinds are pulled; the renderer filters what it needs.
    """
    fb = FactBuilder()
    inputs: dict[str, list] = {
        "changes": [],
        "impacts": [],
        "validation": [],
        "dependencies": [],
    }

    focus_id = _doc_id_for_number(db, project_id, document_number)

    # Dependencies
    dep_stmt = select(Dependency).where(Dependency.project_id == project_id)
    if focus_id:
        dep_stmt = dep_stmt.where(
            (Dependency.source_document_id == focus_id)
            | (Dependency.target_document_id == focus_id)
        )
    deps = list(db.scalars(dep_stmt))
    dep_numbers = _doc_numbers(
        db,
        {d.source_document_id for d in deps} | {d.target_document_id for d in deps},
    )
    for d in deps:
        inputs["dependencies"].append(
            {
                "source": dep_numbers.get(d.source_document_id, d.source_document_id),
                "target": dep_numbers.get(d.target_document_id, d.target_document_id),
                "type": d.relationship_type.replace("_", " "),
            }
        )

    # Impact events
    imp_stmt = select(ImpactEvent).where(ImpactEvent.project_id == project_id)
    if focus_id:
        imp_stmt = imp_stmt.where(
            (ImpactEvent.changed_document_id == focus_id)
            | (ImpactEvent.impacted_document_id == focus_id)
        )
    imps = list(db.scalars(imp_stmt))
    imp_numbers = _doc_numbers(
        db,
        {i.changed_document_id for i in imps} | {i.impacted_document_id for i in imps},
    )
    for i in imps:
        inputs["impacts"].append(
            {
                "source": imp_numbers.get(i.changed_document_id, i.changed_document_id),
                "target": imp_numbers.get(i.impacted_document_id, i.impacted_document_id),
                "severity": i.severity,
            }
        )

    # Validation issues (only when the question type cares)
    if question_type in (
        QuestionType.VALIDATION,
        QuestionType.STATUS,
        QuestionType.SUMMARY,
        QuestionType.UNKNOWN,
    ):
        val_stmt = select(ValidationIssue).where(ValidationIssue.project_id == project_id)
        if document_number:
            val_stmt = val_stmt.where(ValidationIssue.document_number == document_number)
        for v in db.scalars(val_stmt):
            inputs["validation"].append(
                {
                    "document_number": v.document_number,
                    "revision": None,
                    "message": v.message or v.title or v.rule_id,
                }
            )

    return fb.build(inputs)