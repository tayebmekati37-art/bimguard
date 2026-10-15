"""Deterministic question router.

No DB, no network, no AI. Maps a natural-language question to one of a
fixed set of question types. First matching rule wins.
"""
from __future__ import annotations

import re
from enum import Enum


class QuestionType(str, Enum):
    AFFECTED_BY = "affected_by"   # what is affected by X
    AFFECTS = "affects"           # what does X affect
    STATUS = "status"             # status of X / is X stale
    VALIDATION = "validation"     # validation issues / problems with X
    DEPENDENCIES = "dependencies" # what depends on X / dependencies of X
    SUMMARY = "summary"           # summarize / summary of
    UNKNOWN = "unknown"


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


# Ordered rules. First match wins.
_RULES: list[tuple[QuestionType, re.Pattern[str]]] = [
    # AFFECTED_BY: "what is affected by X", "what documents are affected by X"
    (QuestionType.AFFECTED_BY, re.compile(
        r"\b(?:what|which|who)\b.*\baffected\s+by\b"
        r"|\baffected\s+by\b.*\b(?:what|which)\b"
    )),
    # AFFECTS: "what does X affect", "what does X impact"
    (QuestionType.AFFECTS, re.compile(
        r"\bwhat\s+does\b.*\b(?:affect|impact)\b"
        r"|\bwhat\b.*\b(?:affect|impact)s?\b(?!.*\bby\b)"
    )),
    # SUMMARY before STATUS so "summary of status" routes to SUMMARY
    (QuestionType.SUMMARY, re.compile(
        r"\bsummari[sz]e\b"
        r"|\bsummary\s+of\b"
        r"|\boverview\s+of\b"
    )),
    # VALIDATION
    (QuestionType.VALIDATION, re.compile(
        r"\bvalidation\s+issues?\b"
        r"|\bvalidation\b"
        r"|\bproblems?\s+with\b"
        r"|\bissues?\s+with\b"
        r"|\bwhat\s+is\s+wrong\s+with\b"
    )),
    # DEPENDENCIES
    (QuestionType.DEPENDENCIES, re.compile(
        r"\bdepends?\s+on\b"
        r"|\bdependenc(?:y|ies)\b"
        r"|\brelated\s+to\b"
    )),
    # STATUS
    (QuestionType.STATUS, re.compile(
        r"\bstatus\s+of\b"
        r"|\bis\b.*\bstale\b"
        r"|\bstale\b"
        r"|\bwhat\s+state\s+is\b"
    )),
]


class Router:
    """Classify a question into a fixed QuestionType."""

    def route(self, question: str) -> QuestionType:
        if not question or not question.strip():
            return QuestionType.UNKNOWN
        text = _norm(question)
        for qtype, pattern in _RULES:
            if pattern.search(text):
                return qtype
        return QuestionType.UNKNOWN