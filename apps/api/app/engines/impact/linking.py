"""Finds which elements of a dependent document are plausibly affected by the changes made upstream.

Four deterministic rules, strongest first: counterpart (same class and tag), reference (the element lists the
changed element in a `BasedOn` property), proximity (outlines within a distance in plan), same room.
"""
from collections.abc import Sequence

from app.bim.types import ElementData
from app.engines.impact.geometry import footprint_polygon, polygon_distance
from app.engines.impact.types import AffectedElement, ChangedElement, ImpactConfig

_PRIORITY = {"counterpart": 4, "references": 3, "proximity": 2, "same_room": 1}
_GEOMETRIC = {"GEOMETRY_CHANGED", "ELEMENT_ADDED", "ELEMENT_REMOVED"}
_MAX_REASONS = 4


def _label(ifc_class: str, tag: str) -> str:
    return f"{ifc_class[3:] if ifc_class.startswith('Ifc') else ifc_class} {tag}"


def _references(element: ElementData) -> set[str]:
    value = element.properties.get("BasedOn")
    if isinstance(value, (list, tuple)):
        return {str(v) for v in value}
    return {str(value)} if value else set()


def _num(x: float) -> str:
    return f"{x:.0f}"


def link_elements(changed: Sequence[ChangedElement], dependents: Sequence[ElementData],
                  config: ImpactConfig) -> tuple[list[AffectedElement], int]:
    """Returns the strongest `max_affected_elements` links and the total number of affected elements."""
    changed = list(changed)[:config.max_changed_elements_for_linking]
    outlines = {}
    for ch in changed:
        if _GEOMETRIC & set(ch.change_types):
            outlines[ch.guid] = (footprint_polygon(ch.new_geometry), footprint_polygon(ch.old_geometry))

    found: list[tuple[AffectedElement, int, float]] = []
    for e in dependents:
        kinds: dict[str, None] = {}
        reasons: list[str] = []
        distance: float | None = None
        refs = _references(e)
        mine = footprint_polygon(e.geometry)
        for ch in changed:
            where = _label(ch.ifc_class, ch.tag)
            if ch.tag and e.tag == ch.tag and e.ifc_class == ch.ifc_class:
                kinds["counterpart"] = None
                reasons.append(f"Corresponds to {where} in the changed document ({ch.summary})")
            if ch.tag in refs or ch.guid in refs:
                kinds["references"] = None
                reasons.append(f"Based on {where} ({ch.summary})")
            if mine is not None and ch.guid in outlines and not (e.level and ch.level and e.level != ch.level):
                after, before = outlines[ch.guid]
                theirs = after or before
                if theirs is not None:
                    d = polygon_distance(mine, theirs)
                    if d <= config.proximity_mm:
                        kinds["proximity"] = None
                        distance = d if distance is None else min(distance, d)
                        reasons.append(f"Overlaps or touches {where} after the change" if d == 0 else
                                       f"{_num(d)} mm from {where} after the change")
            if e.room and e.room in ch.rooms:
                kinds["same_room"] = None
                reasons.append(f"In room {e.room}, where {where} changed")
        if kinds:
            top = max(_PRIORITY[k] for k in kinds)
            found.append((AffectedElement(
                guid=e.guid, tag=e.tag, name=e.name, ifc_class=e.ifc_class, room=e.room,
                kinds=tuple(sorted(kinds, key=lambda k: -_PRIORITY[k])),
                reasons=tuple(dict.fromkeys(reasons))[:_MAX_REASONS], distance_mm=distance), top,
                distance if distance is not None else float("inf")))
    found.sort(key=lambda t: (-t[1], t[2], t[0].tag, t[0].guid))
    return [f[0] for f in found[:config.max_affected_elements]], len(found)
