"""Deterministic fact construction for BIMGuard's optional AI layer.

This module has no database, network, asynchronous, or AI dependencies.
It converts structured engine records into short, traceable sentences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Fact:
    """One deterministic statement derived from engine data."""

    text: str
    kind: str
    identifiers: list[str]


_IDENTIFIER_PATTERN = re.compile(
    r"https?://[^\s<>\"'\])}]+"
    r"|www\.[^\s<>\"'\])}]+"
    r"|\brevision\s+(?:v\d+|\d+|[A-Za-z][A-Za-z0-9_-]*)\b"
    r"|\bv\d+\b"
    r"|\b[A-Za-z]{1,6}-[A-Za-z0-9]{1,4}(?:-[A-Za-z0-9]{1,4})?\b",
    re.IGNORECASE,
)

_DOCUMENT_KEYS = (
    "document_number", "document_no", "doc_number", "doc_no",
    "document_code", "doc_code", "document", "doc",
)
_ELEMENT_KEYS = (
    "element_tag", "element_ref", "ifc_tag", "tag",
    "element_id", "global_id", "ifc_guid", "element",
)
_REVISION_KEYS = ("revision", "rev", "version")


def _get(source: Any, *keys: str) -> Any:
    """Read the first present key from a dict or attribute from an object."""
    if source is None:
        return None
    for key in keys:
        if isinstance(source, dict):
            if source.get(key) is not None:
                return source[key]
        else:
            value = getattr(source, key, None)
            if value is not None:
                return value
    return None


def _extract_identifiers(text: str) -> list[str]:
    """Return identifiers found in text, in first-seen order, deduped."""
    seen: list[str] = []
    for match in _IDENTIFIER_PATTERN.finditer(text):
        token = match.group(0).strip()
        if token and token not in seen:
            seen.append(token)
    return seen


class FactBuilder:
    """Turn structured engine records into deterministic Fact objects."""

    def from_change(self, change: Any) -> Fact:
        doc = _get(change, *_DOCUMENT_KEYS) or "unknown document"
        rev = _get(change, *_REVISION_KEYS)
        element = _get(change, *_ELEMENT_KEYS)
        field = _get(change, "field", "field_name", "attribute")
        old = _get(change, "old_value", "old")
        new = _get(change, "new_value", "new")

        parts = [f"Change recorded for document {doc}"]
        if rev:
            parts.append(f"at revision {rev}")
        if element:
            parts.append(f"on element {element}")
        if field and (old is not None or new is not None):
            parts.append(f"; {field} changed from {old} to {new}")
        text = " ".join(parts).replace(" ;", ";") + "."
        identifiers = _extract_identifiers(text)
        return Fact(text=text, kind="change", identifiers=identifiers)

    def from_impact(self, impact: Any) -> Fact:
        source = _get(impact, "source", "source_document", "from_document") or "unknown source"
        target = _get(impact, "target", "target_document", "to_document") or "unknown target"
        severity = _get(impact, "severity", "level") or "unknown"
        text = f"{str(severity).capitalize()} impact on {target} from {source}."
        identifiers = _extract_identifiers(text)
        return Fact(text=text, kind="impact", identifiers=identifiers)

    def from_validation(self, issue: Any) -> Fact:
        doc = _get(issue, *_DOCUMENT_KEYS) or "unknown document"
        rev = _get(issue, *_REVISION_KEYS)
        message = _get(issue, "message", "description", "rule") or "validation issue"
        if rev:
            text = f"{doc} at revision {rev} has validation issue: {message}."
        else:
            text = f"{doc} has validation issue: {message}."
        identifiers = _extract_identifiers(text)
        return Fact(text=text, kind="validation", identifiers=identifiers)

    def from_dependency(self, edge: Any) -> Fact:
        source = _get(edge, "source", "from_document", "parent") or "unknown source"
        target = _get(edge, "target", "to_document", "child") or "unknown target"
        rel = _get(edge, "type", "relation", "kind") or "depends on"
        text = f"{source} {rel} {target}."
        identifiers = _extract_identifiers(text)
        return Fact(text=text, kind="dependency", identifiers=identifiers)

    def build(self, all_inputs: dict[str, list[Any]]) -> list[Fact]:
        """Build Facts from a dict of {kind: [records]}."""
        facts: list[Fact] = []
        for change in all_inputs.get("changes", []) or []:
            facts.append(self.from_change(change))
        for impact in all_inputs.get("impacts", []) or []:
            facts.append(self.from_impact(impact))
        for issue in all_inputs.get("validation", []) or []:
            facts.append(self.from_validation(issue))
        for edge in all_inputs.get("dependencies", []) or []:
            facts.append(self.from_dependency(edge))

        seen: set[tuple[str, str]] = set()
        deduped: list[Fact] = []
        for f in facts:
            key = (f.text, f.kind)
            if key not in seen:
                seen.add(key)
                deduped.append(f)
        return deduped