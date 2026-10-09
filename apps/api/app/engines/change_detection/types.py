from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ChangeType(str, Enum):
    ELEMENT_ADDED = "ELEMENT_ADDED"
    ELEMENT_REMOVED = "ELEMENT_REMOVED"
    GEOMETRY_CHANGED = "GEOMETRY_CHANGED"
    PARAMETER_CHANGED = "PARAMETER_CHANGED"
    SPATIAL_CHANGED = "SPATIAL_CHANGED"
    CLASSIFICATION_CHANGED = "CLASSIFICATION_CHANGED"
    METADATA_CHANGED = "METADATA_CHANGED"
    REFERENCE_CHANGED = "REFERENCE_CHANGED"  # produced from document relationships (Milestone 5)


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_ORDER = (Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def bump(severity: Severity) -> Severity:
    return SEVERITY_ORDER[min(SEVERITY_ORDER.index(severity) + 1, len(SEVERITY_ORDER) - 1)]


@dataclass(frozen=True)
class ChangeDetectionConfig:
    """Every threshold and weight used by the engine. A snapshot is stored with each comparison."""

    # Tolerances: differences at or below these are treated as "no change".
    position_tolerance_mm: float = 1.0
    dimension_tolerance_mm: float = 1.0
    rotation_tolerance_deg: float = 0.1
    numeric_tolerance: float = 0.001
    # Severity bands for movement / resizing / rotation.
    move_medium_mm: float = 100.0
    move_high_mm: float = 500.0
    rotation_medium_deg: float = 1.0
    rotation_high_deg: float = 5.0
    quantity_relative_medium: float = 0.01
    # Parameter names (last segment of "PsetName.Property") by importance.
    critical_parameters: tuple[str, ...] = ("LoadBearing", "FireRating", "IsExternal")
    significant_parameters: tuple[str, ...] = (
        "OccupancyType", "NominalAirflowM3h", "PowerKW", "Span", "Voltage", "VolumeLitres")
    # Elements whose addition/removal/movement matters more.
    structural_classes: tuple[str, ...] = ("IfcColumn", "IfcBeam", "IfcSlab", "IfcFooting", "IfcMember", "IfcPile")
    high_impact_add_remove_classes: tuple[str, ...] = (
        "IfcColumn", "IfcBeam", "IfcSlab", "IfcFooting", "IfcMember", "IfcPile", "IfcSpace")
    # Confidence model (see docs/architecture/change-detection.md).
    guid_match_confidence: float = 0.99
    tag_match_confidence: float = 0.85
    unambiguous_add_remove_confidence: float = 0.97
    ambiguous_add_remove_confidence: float = 0.80
    near_tolerance_factor: float = 5.0
    near_tolerance_confidence_factor: float = 0.9

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CONFIG = ChangeDetectionConfig()


@dataclass(frozen=True)
class RevisionMeta:
    status: str
    model_schema: str | None


@dataclass(frozen=True)
class Change:
    change_type: ChangeType
    element_guid: str | None
    element_tag: str
    element_name: str
    ifc_class: str
    field: str
    old_value: Any
    new_value: Any
    severity: Severity
    confidence: float
    summary: str
    match_method: str = "guid"  # "guid" | "tag" | "none"
    detail: dict[str, Any] = field(default_factory=dict)
