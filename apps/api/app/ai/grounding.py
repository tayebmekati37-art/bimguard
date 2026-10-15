"""Deterministic grounding check.

Extracts identifiers from a model reply and verifies each one appears in
the fact set. Any identifier not present in the facts is a violation.
No DB, no network, no AI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.ai.facts import Fact


@dataclass(frozen=True)
class GroundingResult:
    ok: bool
    violations: list[str]


_IDENTIFIER_PATTERN = re.compile(
    r"https?://[^\s<>\"'\])}]+"
    r"|www\.[^\s<>\"'\])}]+"
    r"|\brevision\s+(?:v\d+|\d+)\b"
    r"|\bv\d+\b"
    r"|\b[A-Za-z]{1,6}-\d{1,4}(?:-[A-Za-z0-9]{1,4})?\b",
    re.IGNORECASE,
)

_TRAILING_PUNCT = ".,;:!?"


def _extract(text: str) -> list[str]:
    seen: list[str] = []
    for m in _IDENTIFIER_PATTERN.finditer(text):
        token = m.group(0).strip().rstrip(_TRAILING_PUNCT)
        if token and token not in seen:
            seen.append(token)
    return seen


def _known_set(facts: Iterable[Fact]) -> set[str]:
    known: set[str] = set()
    for f in facts:
        for ident in f.identifiers:
            known.add(ident.lower())
    return known


def _is_known(token: str, known: set[str]) -> bool:
    low = token.lower()
    if low in known:
        return True
    pattern = r"(?<![A-Za-z0-9])" + re.escape(low) + r"(?![A-Za-z0-9])"
    for k in known:
        if re.search(pattern, k):
            return True
    return False


def check(reply: str, facts: list[Fact]) -> GroundingResult:
    known = _known_set(facts)
    violations: list[str] = []
    seen: set[str] = set()
    for token in _extract(reply):
        low = token.lower()
        if low in seen:
            continue
        if _is_known(token, known):
            continue
        violations.append(f"unknown identifier: {token}")
        seen.add(low)
    return GroundingResult(ok=not violations, violations=violations)