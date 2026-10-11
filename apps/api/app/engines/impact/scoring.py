"""Impact score = 100 x dependency x change x propagation x status, each factor between 0 and 1.

dependency   weakest relationship on the path (relationship type weight x confidence)
change       strongest change, weighted by severity, change type and how relevant that kind of element is to
             the dependent discipline, plus a small bonus for each additional change
propagation  decays with every hop beyond the first
status       how consequential stale information is in the dependent document (issued > draft), times how
             official the changed revision is
"""
from collections.abc import Sequence
from dataclasses import dataclass

from app.engines.change_detection.types import Severity
from app.engines.graph import FLOW, Flow, Impacted, PathStep, RelationshipType
from app.engines.impact.types import ChangeInput, DocumentInfo, Factor, ImpactConfig

_WALLS = ("IfcWall", "IfcCurtainWall")
_STRUCTURAL = ("IfcColumn", "IfcBeam", "IfcSlab", "IfcFooting", "IfcMember", "IfcPile", "IfcStair", "IfcRamp")
_OPENINGS = ("IfcDoor", "IfcWindow")
_DISTRIBUTION_PREFIXES = ("IfcDuct", "IfcPipe", "IfcFlow", "IfcUnitary", "IfcAir", "IfcPump", "IfcFan", "IfcBoiler",
                          "IfcChiller", "IfcCable", "IfcElectric", "IfcLamp", "IfcLight", "IfcSensor", "IfcValve",
                          "IfcTank", "IfcCompressor", "IfcDistribution")

_PHRASES = {
    RelationshipType.DEPENDS_ON: "depends on", RelationshipType.REFERENCES: "references",
    RelationshipType.GENERATED_FROM: "is generated from", RelationshipType.DERIVED_FROM: "is derived from",
    RelationshipType.QUANTITY_BASED_ON: "has quantities based on", RelationshipType.VALIDATION_SOURCE: "is validated against",
    RelationshipType.APPROVAL_DEPENDENCY: "needs approval of", RelationshipType.AFFECTS: "affects",
    RelationshipType.SPATIALLY_RELATED_TO: "is spatially related to",
}


def class_group(ifc_class: str) -> str:
    if ifc_class in _WALLS:
        return "wall"
    if ifc_class in _STRUCTURAL:
        return "structural"
    if ifc_class in _OPENINGS:
        return "opening"
    if ifc_class == "IfcSpace":
        return "space"
    if ifc_class.startswith(_DISTRIBUTION_PREFIXES):
        return "distribution"
    return "other"


def change_contribution(change: ChangeInput, discipline: str, config: ImpactConfig) -> float:
    relevance_row = config.relevance.get(discipline, {})
    relevance = relevance_row.get(class_group(change.ifc_class), config.default_relevance)
    return (config.severity_weights.get(change.severity, 0.3)
            * config.change_type_weights.get(change.change_type, 0.5) * relevance)


def step_phrase(step: PathStep, names: dict[str, str]) -> str:
    """'S-201 depends on A-101' for a step that carries a change from A-101 to S-201."""
    source, target = names[step.from_node], names[step.to_node]
    flow = FLOW[step.relationship_type]
    if flow == Flow.TARGET_TO_SOURCE:  # the consumer holds the relationship
        return f"{target} {_PHRASES[step.relationship_type]} {source}"
    return f"{source} {_PHRASES[step.relationship_type]} {target}"


@dataclass(frozen=True)
class Scored:
    score: float
    severity: Severity
    confidence: float
    factors: tuple[Factor, ...]
    formula: str
    driver: ChangeInput | None


def score_impact(*, dependent: DocumentInfo, impacted: Impacted, provider_status: str,
                 changes: Sequence[ChangeInput], config: ImpactConfig) -> Scored:
    discipline = dependent.discipline
    contributions = sorted(((change_contribution(c, discipline, config), c) for c in changes),
                           key=lambda t: (-t[0], t[1].tag, t[1].change_type))
    best, driver = contributions[0] if contributions else (0.0, None)
    bonus = min(config.max_change_bonus, config.additional_change_bonus * max(0, len(contributions) - 1))
    change_weight = min(1.0, best + bonus)

    weakest = min(impacted.path, key=lambda s: (s.strength, s.edge_id))
    dependency = weakest.strength
    propagation = config.propagation_decay ** (impacted.distance - 1)
    dependent_status = config.dependent_status_weights.get(dependent.status, config.default_status_weight)
    provider_weight = config.provider_status_weights.get(provider_status, config.default_status_weight)
    status = dependent_status * provider_weight

    score = round(100.0 * dependency * change_weight * propagation * status, 1)
    group = class_group(driver.ifc_class) if driver else "other"
    factors = (
        Factor("dependency", "Dependency strength", round(dependency, 3),
               f"Weakest link on the path: {weakest.relationship_type.value.replace('_', ' ')} at "
               f"{round(dependency * 100)}% (relationship weight x confidence)."),
        Factor("change", "Change weight", round(change_weight, 3),
               (f"Strongest change: {driver.summary} ({driver.severity.lower()} {driver.change_type.replace('_', ' ').lower()}, "
                f"{group} relevance to {discipline} documents = {config.relevance.get(discipline, {}).get(group, config.default_relevance):.2f})"
                f"{f', plus {bonus:.2f} for {len(contributions) - 1} more changes' if bonus else ''}.") if driver
               else "No detected changes."),
        Factor("propagation", "Distance", round(propagation, 3),
               "Direct dependency." if impacted.distance == 1 else
               f"{impacted.distance} steps away; each extra step multiplies by {config.propagation_decay}."),
        Factor("status", "Status", round(status, 3),
               f"{dependent.number} is {dependent.status.replace('_', ' ')} ({dependent_status:.2f}); the changed "
               f"revision is {provider_status.replace('_', ' ')} ({provider_weight:.2f})."),
    )
    formula = (f"100 x {dependency:.2f} x {change_weight:.2f} x {propagation:.2f} x {status:.2f} = {score:.1f}")
    confidence = round(min(s.confidence for s in impacted.path)
                       * (driver.confidence if driver else 1.0)
                       * config.distance_confidence_decay ** (impacted.distance - 1), 2)
    return Scored(score, config.classify(score), confidence, factors, formula, driver)
