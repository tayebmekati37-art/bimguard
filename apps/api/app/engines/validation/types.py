import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.engines.graph import Edge

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
CATEGORIES = ("revision", "dependency", "consistency", "metadata", "naming", "approval", "policy")


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity)


@dataclass(frozen=True)
class RuleConfig:
    rule_id: str
    enabled: bool
    severity: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RevisionState:
    number: int
    status: str
    checksum: str = ""
    change_summary: str = ""


@dataclass(frozen=True)
class DocumentState:
    id: str
    number: str
    name: str
    discipline: str
    status: str
    author: str = ""
    source_system: str = ""
    current_revision_number: int | None = None
    revisions: tuple[RevisionState, ...] = ()


@dataclass(frozen=True)
class AffectedRef:
    tag: str
    kinds: tuple[str, ...]
    distance_mm: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OpenImpact:
    """An impact that has not been reviewed yet (see Milestone 6)."""

    event_id: str
    impacted_document_id: str
    changed_document_number: str
    changed_revision_number: int
    direct: bool
    severity: str
    score: float
    first_hop_number: str
    affected: tuple[AffectedRef, ...] = ()
    affected_total: int = 0


@dataclass(frozen=True)
class ElementReferences:
    tag: str
    refs: tuple[str, ...]


@dataclass(frozen=True)
class ElementSummary:
    """The narrow slice of a BimElement that cross-document checks compare.

    Only level, room and material are included. Those are the fields that
    every IFC extractor reliably populates and that mean the same thing
    across disciplines. Geometry is deliberately absent: BIMGuard does not
    tessellate, so comparing shapes here would be inventing evidence.
    """

    tag: str
    level: str | None = None
    room: str | None = None
    material: str | None = None


@dataclass(frozen=True)
class Snapshot:
    """Everything the rules look at, loaded once. Rules never touch the database."""

    documents: tuple[DocumentState, ...]
    edges: tuple[Edge, ...] = ()
    open_impacts: tuple[OpenImpact, ...] = ()
    references: Mapping[str, tuple[ElementReferences, ...]] = field(default_factory=dict)
    tags: Mapping[str, frozenset[str]] = field(default_factory=dict)
    properties: Mapping[str, Mapping[str, Mapping[str, Any]]] = field(default_factory=dict)
    elements_by_document: Mapping[str, Mapping[str, ElementSummary]] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    document_id: str | None
    document_number: str
    title: str
    message: str
    recommended_action: str
    subject: str            # what the finding is about, for example a dependency id or an element tag
    evidence: str           # the state it was observed in, so a changed situation is a new finding
    element_tag: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        raw = f"{self.rule_id}|{self.document_id}|{self.subject}|{self.evidence}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class Readiness:
    status: str  # BLOCKED | READY_WITH_WARNINGS | READY
    open_count: int
    acknowledged_count: int
    blocking_count: int
    open_by_severity: dict[str, int]
    by_rule: dict[str, int]
