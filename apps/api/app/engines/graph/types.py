from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class RelationshipType(str, Enum):
    DEPENDS_ON = "depends_on"
    AFFECTS = "affects"
    REFERENCES = "references"
    GENERATED_FROM = "generated_from"
    DERIVED_FROM = "derived_from"
    SPATIALLY_RELATED_TO = "spatially_related_to"
    QUANTITY_BASED_ON = "quantity_based_on"
    VALIDATION_SOURCE = "validation_source"
    APPROVAL_DEPENDENCY = "approval_dependency"


class Flow(str, Enum):
    """Which way a change travels. 'S depends_on T' means information flows T -> S: changing T can outdate S."""

    TARGET_TO_SOURCE = "target_to_source"
    SOURCE_TO_TARGET = "source_to_target"
    BOTH = "both"


FLOW: dict[RelationshipType, Flow] = {
    RelationshipType.DEPENDS_ON: Flow.TARGET_TO_SOURCE,
    RelationshipType.AFFECTS: Flow.SOURCE_TO_TARGET,
    RelationshipType.REFERENCES: Flow.TARGET_TO_SOURCE,
    RelationshipType.GENERATED_FROM: Flow.TARGET_TO_SOURCE,
    RelationshipType.DERIVED_FROM: Flow.TARGET_TO_SOURCE,
    RelationshipType.SPATIALLY_RELATED_TO: Flow.BOTH,
    RelationshipType.QUANTITY_BASED_ON: Flow.TARGET_TO_SOURCE,
    RelationshipType.VALIDATION_SOURCE: Flow.TARGET_TO_SOURCE,
    RelationshipType.APPROVAL_DEPENDENCY: Flow.TARGET_TO_SOURCE,
}

# How strongly a change travels along each kind of relationship (0..1). A structural dependency matters
# far more than a casual reference. Configurable, and multiplied by the edge's own confidence.
DEFAULT_TYPE_WEIGHTS: dict[RelationshipType, float] = {
    RelationshipType.DEPENDS_ON: 1.0,
    RelationshipType.AFFECTS: 0.9,
    RelationshipType.QUANTITY_BASED_ON: 0.9,
    RelationshipType.DERIVED_FROM: 0.85,
    RelationshipType.GENERATED_FROM: 0.85,
    RelationshipType.APPROVAL_DEPENDENCY: 0.7,
    RelationshipType.VALIDATION_SOURCE: 0.7,
    RelationshipType.SPATIALLY_RELATED_TO: 0.6,
    RelationshipType.REFERENCES: 0.3,
}


@dataclass(frozen=True)
class GraphConfig:
    type_weights: Mapping[RelationshipType, float] = field(default_factory=lambda: dict(DEFAULT_TYPE_WEIGHTS))

    def to_dict(self) -> dict[str, float]:
        return {t.value: w for t, w in self.type_weights.items()}


DEFAULT_GRAPH_CONFIG = GraphConfig()


@dataclass(frozen=True)
class Edge:
    id: str
    source: str  # document id of the document that holds the relationship
    target: str
    relationship_type: RelationshipType
    confidence: float = 1.0
    reason: str = ""
    validated_against_revision: int | None = None

    @property
    def flow(self) -> Flow:
        return FLOW[self.relationship_type]

    @property
    def provider(self) -> str | None:
        """The document whose changes this edge carries; None for symmetric relationships."""
        if self.flow == Flow.TARGET_TO_SOURCE:
            return self.target
        if self.flow == Flow.SOURCE_TO_TARGET:
            return self.source
        return None

    @property
    def consumer(self) -> str | None:
        if self.flow == Flow.TARGET_TO_SOURCE:
            return self.source
        if self.flow == Flow.SOURCE_TO_TARGET:
            return self.target
        return None

    def strength(self, config: GraphConfig = DEFAULT_GRAPH_CONFIG) -> float:
        return round(config.type_weights[self.relationship_type] * self.confidence, 6)


def is_stale(edge: Edge, provider_current_revision: int | None) -> bool:
    """A consumer is stale when its provider has moved past the revision it was validated against.
    Symmetric relationships carry no direction, so they are never reported stale."""
    if edge.provider is None or provider_current_revision is None:
        return False
    validated = edge.validated_against_revision
    return validated is None or provider_current_revision > validated


@dataclass(frozen=True)
class PathStep:
    edge_id: str
    from_node: str
    to_node: str
    relationship_type: RelationshipType
    strength: float
    reason: str
    confidence: float = 1.0


@dataclass(frozen=True)
class Impacted:
    node: str
    distance: int
    strength: float
    path: tuple[PathStep, ...]

    @property
    def direct(self) -> bool:
        return self.distance == 1
