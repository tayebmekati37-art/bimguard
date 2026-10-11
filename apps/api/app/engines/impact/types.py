from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.engines.change_detection.types import Severity
from app.engines.graph import PathStep


def _severity_weights() -> dict[str, float]:
    return {"LOW": 0.30, "MEDIUM": 0.60, "HIGH": 0.85, "CRITICAL": 1.0}


def _change_type_weights() -> dict[str, float]:
    return {"GEOMETRY_CHANGED": 1.0, "ELEMENT_ADDED": 1.0, "ELEMENT_REMOVED": 1.0, "SPATIAL_CHANGED": 0.9,
            "CLASSIFICATION_CHANGED": 0.9, "PARAMETER_CHANGED": 0.7, "METADATA_CHANGED": 0.3,
            "REFERENCE_CHANGED": 0.8}


def _relevance() -> dict[str, dict[str, float]]:
    """How much a change to an element of this kind matters to a document of this discipline."""
    def row(wall, structural, opening, space, distribution, other):
        return {"wall": wall, "structural": structural, "opening": opening, "space": space,
                "distribution": distribution, "other": other}
    return {
        "architecture": row(1.0, 0.8, 1.0, 1.0, 0.5, 0.6),
        "structure": row(1.0, 1.0, 0.4, 0.7, 0.3, 0.5),
        "mep": row(0.9, 0.6, 0.6, 1.0, 0.9, 0.5),
        "equipment": row(0.7, 0.5, 0.4, 1.0, 0.8, 0.5),
        "quantity": row(1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        "general": row(0.6, 0.6, 0.6, 0.6, 0.6, 0.6),
    }


def _dependent_status() -> dict[str, float]:
    return {"issued": 1.0, "approved": 0.95, "in_review": 0.85, "draft": 0.7, "rejected": 0.5, "superseded": 0.3}


def _provider_status() -> dict[str, float]:
    return {"issued": 1.0, "approved": 1.0, "in_review": 0.9, "draft": 0.8, "rejected": 0.5, "superseded": 0.5}


@dataclass(frozen=True)
class ImpactConfig:
    """Every weight in the impact score. A snapshot is stored with each analysis."""

    severity_weights: Mapping[str, float] = field(default_factory=_severity_weights)
    change_type_weights: Mapping[str, float] = field(default_factory=_change_type_weights)
    relevance: Mapping[str, Mapping[str, float]] = field(default_factory=_relevance)
    default_relevance: float = 0.6
    additional_change_bonus: float = 0.03   # per extra change beyond the strongest
    max_change_bonus: float = 0.15
    propagation_decay: float = 0.7          # multiplied once per hop beyond the first
    distance_confidence_decay: float = 0.9
    dependent_status_weights: Mapping[str, float] = field(default_factory=_dependent_status)
    provider_status_weights: Mapping[str, float] = field(default_factory=_provider_status)
    default_status_weight: float = 0.7
    band_medium: float = 25.0
    band_high: float = 50.0
    band_critical: float = 75.0
    # element-level linking
    proximity_mm: float = 1000.0
    max_affected_elements: int = 25
    max_changed_elements_for_linking: int = 500
    max_elements_for_element_analysis: int = 50000

    def to_dict(self) -> dict[str, Any]:
        return {k: (dict(v) if isinstance(v, Mapping) else v) for k, v in self.__dict__.items()}

    def classify(self, score: float) -> Severity:
        if score >= self.band_critical:
            return Severity.CRITICAL
        if score >= self.band_high:
            return Severity.HIGH
        return Severity.MEDIUM if score >= self.band_medium else Severity.LOW


DEFAULT_IMPACT_CONFIG = ImpactConfig()


@dataclass(frozen=True)
class DocumentInfo:
    id: str
    number: str
    discipline: str
    status: str
    current_revision_number: int | None = None


@dataclass(frozen=True)
class ChangeInput:
    change_type: str
    severity: str
    confidence: float
    ifc_class: str
    tag: str
    summary: str


@dataclass(frozen=True)
class ChangedElement:
    guid: str
    tag: str
    ifc_class: str
    change_types: tuple[str, ...]
    summary: str
    rooms: frozenset[str] = frozenset()
    level: str | None = None
    old_geometry: dict | None = None
    new_geometry: dict | None = None


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    value: float
    explanation: str


@dataclass(frozen=True)
class AffectedElement:
    guid: str
    tag: str
    name: str
    ifc_class: str
    room: str | None
    kinds: tuple[str, ...]
    reasons: tuple[str, ...]
    distance_mm: float | None


@dataclass(frozen=True)
class ImpactResult:
    document_id: str
    distance: int
    direct: bool
    score: float
    severity: Severity
    confidence: float
    reason: str
    factors: tuple[Factor, ...]
    formula: str
    path: tuple[PathStep, ...]
    first_edge_id: str | None
    driver_summary: str
    affected_elements: tuple[AffectedElement, ...] = ()
    affected_element_count: int = 0
    note: str = ""
