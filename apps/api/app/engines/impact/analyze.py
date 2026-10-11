from collections.abc import Mapping, Sequence

from app.bim.types import ElementData
from app.engines.graph import DependencyGraph
from app.engines.impact.linking import link_elements
from app.engines.impact.scoring import score_impact, step_phrase
from app.engines.impact.types import (
    DEFAULT_IMPACT_CONFIG, ChangedElement, ChangeInput, DocumentInfo, ImpactConfig, ImpactResult,
)


def analyze_impact(
    *, graph: DependencyGraph, root: DocumentInfo, root_revision: int | None, root_status: str,
    documents: Mapping[str, DocumentInfo], changes: Sequence[ChangeInput],
    changed_elements: Sequence[ChangedElement] = (), dependent_elements: Mapping[str, Sequence[ElementData]] | None = None,
    element_notes: Mapping[str, str] | None = None, config: ImpactConfig = DEFAULT_IMPACT_CONFIG,
) -> list[ImpactResult]:
    """Propagates the changes of `root` through the dependency graph and scores every document they can reach.
    Pure and deterministic: the same inputs always give the same ordered results."""
    if not changes:
        return []
    names = {d.id: d.number for d in documents.values()}
    dependent_elements, element_notes = dependent_elements or {}, element_notes or {}
    results: list[ImpactResult] = []
    for impacted in graph.impact_from(root.id):
        dependent = documents[impacted.node]
        scored = score_impact(dependent=dependent, impacted=impacted, provider_status=root_status,
                              changes=changes, config=config)
        driver = scored.driver.summary if scored.driver else ""
        phrases = "; ".join(step_phrase(s, names) for s in impacted.path)
        via = "" if impacted.distance == 1 else f" It is {impacted.distance} steps away ({' > '.join([names[impacted.path[0].from_node]] + [names[s.to_node] for s in impacted.path])})."
        revision = f" v{root_revision}" if root_revision else ""
        reason = (f"{root.number}{revision} ({root.discipline}) changed: {len(changes)} "
                  f"{'change' if len(changes) == 1 else 'changes'}, strongest: {driver}. "
                  f"{phrases[0].upper() + phrases[1:]}.{via} Dependency reason: {impacted.path[-1].reason or 'none recorded'}")
        affected, total = (), 0
        if dependent.id in dependent_elements:
            linked, total = link_elements(changed_elements, dependent_elements[dependent.id], config)
            affected = tuple(linked)
        results.append(ImpactResult(
            document_id=dependent.id, distance=impacted.distance, direct=impacted.direct, score=scored.score,
            severity=scored.severity, confidence=scored.confidence, reason=reason, factors=scored.factors,
            formula=scored.formula, path=impacted.path, first_edge_id=impacted.path[0].edge_id,
            driver_summary=driver, affected_elements=affected, affected_element_count=total,
            note=element_notes.get(dependent.id, "")))
    return sorted(results, key=lambda r: (-r.score, r.distance, names[r.document_id]))
