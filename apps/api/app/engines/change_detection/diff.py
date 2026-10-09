"""Deterministic change detection between two sets of BIM elements.

Pure functions: no database, no network, no randomness, no LLM. The same inputs always produce the same
ordered list of Change records.
"""
import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.bim.types import ElementData
from app.engines.change_detection.types import (
    DEFAULT_CONFIG, Change, ChangeDetectionConfig, ChangeType, RevisionMeta, Severity, bump,
)

_MISSING = object()
_TYPE_ORDER = {t: i for i, t in enumerate(ChangeType)}
_AXES = ("X", "Y", "Z")


# ----------------------------------------------------------------------------- helpers
def _short(ifc_class: str) -> str:
    return ifc_class[3:] if ifc_class.startswith("Ifc") else ifc_class


def _label(e: ElementData) -> str:
    return f"{_short(e.ifc_class)} {e.tag or e.name or e.guid}"


def _num(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def _signed(x: float) -> str:
    return ("+" if x >= 0 else "-") + _num(abs(x))


def _text(value: Any) -> str:
    if value is _MISSING or value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return _num(float(value))
    return str(value)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a: Any, b: Any, tolerance: float) -> bool:
    if _is_number(a) and _is_number(b):
        return round(abs(a - b), 9) <= tolerance
    return a == b


def _band(value: float, medium: float, high: float) -> Severity:
    if value >= high:
        return Severity.HIGH
    return Severity.MEDIUM if value >= medium else Severity.LOW


def _is_load_bearing(e: ElementData) -> bool:
    return any(k.rsplit(".", 1)[-1] == "LoadBearing" and v is True for k, v in e.properties.items())


def _structural(e: ElementData, cfg: ChangeDetectionConfig) -> bool:
    return e.ifc_class in cfg.structural_classes or _is_load_bearing(e)


def _confidence(base: float, delta: float, tolerance: float, cfg: ChangeDetectionConfig) -> float:
    near = delta < cfg.near_tolerance_factor * tolerance
    return round(base * (cfg.near_tolerance_confidence_factor if near else 1.0), 2)


class _Maker:
    """Builds Change records for one element so every record carries the same identity fields."""

    def __init__(self, element: ElementData, method: str, base_confidence: float,
                 extra_detail: dict | None = None) -> None:
        self.e, self.method, self.base = element, method, base_confidence
        self.extra = extra_detail or {}

    def make(self, change_type: ChangeType, field_name: str, old: Any, new: Any, severity: Severity,
             summary: str, confidence: float | None = None, detail: dict | None = None) -> Change:
        return Change(
            change_type=change_type, element_guid=self.e.guid, element_tag=self.e.tag, element_name=self.e.name,
            ifc_class=self.e.ifc_class, field=field_name, old_value=None if old is _MISSING else old,
            new_value=None if new is _MISSING else new, severity=severity,
            confidence=round(self.base if confidence is None else confidence, 2), summary=summary,
            match_method=self.method, detail={**self.extra, **(detail or {})},
        )


# ----------------------------------------------------------------------------- pair comparison
def _geometry_changes(o: ElementData, n: ElementData, mk: _Maker, cfg: ChangeDetectionConfig) -> list[Change]:
    out: list[Change] = []
    og, ng = o.geometry or {}, n.geometry or {}
    label = _label(n)
    structural = _structural(n, cfg)

    def severity(base: Severity) -> Severity:
        return bump(base) if structural else base

    ol, nl = og.get("location"), ng.get("location")
    if ol and nl and len(ol) == len(nl):
        delta = [b - a for a, b in zip(ol, nl)]
        distance = round(math.sqrt(sum(d * d for d in delta)), 6)
        if distance > cfg.position_tolerance_mm:
            axes = ", ".join(f"{_AXES[i]} {_signed(d)}" for i, d in enumerate(delta)
                             if abs(d) > cfg.position_tolerance_mm / 2)
            out.append(mk.make(
                ChangeType.GEOMETRY_CHANGED, "location", ol, nl,
                severity(_band(distance, cfg.move_medium_mm, cfg.move_high_mm)),
                f"{label} moved {_num(distance)} mm ({axes})",
                _confidence(mk.base, distance, cfg.position_tolerance_mm, cfg),
                {"delta_mm": [round(d, 3) for d in delta], "distance_mm": round(distance, 3)}))
    elif bool(ol) != bool(nl):
        out.append(mk.make(
            ChangeType.GEOMETRY_CHANGED, "location", ol, nl, Severity.MEDIUM,
            f"{label} {'gained' if nl else 'lost'} a model location", round(mk.base * 0.9, 2)))

    orot, nrot = og.get("rotation_deg"), ng.get("rotation_deg")
    if _is_number(orot) and _is_number(nrot):
        delta = abs(nrot - orot) % 360
        delta = round(min(delta, 360 - delta), 6)
        if delta > cfg.rotation_tolerance_deg:
            out.append(mk.make(
                ChangeType.GEOMETRY_CHANGED, "rotation_deg", orot, nrot,
                severity(_band(delta, cfg.rotation_medium_deg, cfg.rotation_high_deg)),
                f"{label} rotated by {_num(delta)} deg", _confidence(mk.base, delta, cfg.rotation_tolerance_deg, cfg),
                {"delta_deg": round(delta, 3)}))

    odim, ndim = og.get("dimensions") or {}, ng.get("dimensions") or {}
    dimension_changed = False
    for key in sorted(set(odim) | set(ndim)):
        a, b = odim.get(key, _MISSING), ndim.get(key, _MISSING)
        if a is _MISSING or b is _MISSING:
            dimension_changed = True
            out.append(mk.make(ChangeType.GEOMETRY_CHANGED, f"dimensions.{key}", a, b, Severity.MEDIUM,
                               f"{label} {key.lower()} {'added' if a is _MISSING else 'removed'}",
                               round(mk.base * 0.9, 2)))
        elif round(abs(b - a), 6) > cfg.dimension_tolerance_mm:
            dimension_changed = True
            delta = round(abs(b - a), 6)
            out.append(mk.make(
                ChangeType.GEOMETRY_CHANGED, f"dimensions.{key}", a, b,
                severity(_band(delta, cfg.move_medium_mm, cfg.move_high_mm)),
                f"{label} {key.lower()} changed from {_num(a)} to {_num(b)} mm",
                _confidence(mk.base, delta, cfg.dimension_tolerance_mm, cfg), {"delta_mm": round(b - a, 3)}))

    ofp, nfp = og.get("footprint"), ng.get("footprint")
    if ofp and nfp and not dimension_changed:
        keys = [k for k in sorted(set(ofp) & set(nfp)) if round(abs(nfp[k] - ofp[k]), 6) > cfg.dimension_tolerance_mm]
        if keys:
            delta = max(abs(nfp[k] - ofp[k]) for k in keys)
            out.append(mk.make(
                ChangeType.GEOMETRY_CHANGED, "footprint", ofp, nfp,
                severity(_band(delta, cfg.move_medium_mm, cfg.move_high_mm)),
                f"{label} body extent changed ({', '.join(keys)})",
                _confidence(mk.base, delta, cfg.dimension_tolerance_mm, cfg)))
    return out


def _parameter_severity(key: str, old: Any, new: Any, cfg: ChangeDetectionConfig) -> Severity:
    name = key.rsplit(".", 1)[-1]
    if name in cfg.critical_parameters:
        return Severity.HIGH
    if name in cfg.significant_parameters:
        return Severity.MEDIUM
    if key.split(".", 1)[0].startswith("Qto_") and _is_number(old) and _is_number(new):
        relative = abs(new - old) / max(abs(old), 1e-9)
        if relative >= cfg.quantity_relative_medium:
            return Severity.MEDIUM
    return Severity.LOW


def _parameter_changes(o: ElementData, n: ElementData, mk: _Maker, cfg: ChangeDetectionConfig) -> list[Change]:
    out: list[Change] = []
    label = _label(n)
    for key in sorted(set(o.properties) | set(n.properties)):
        a, b = o.properties.get(key, _MISSING), n.properties.get(key, _MISSING)
        if a is not _MISSING and b is not _MISSING and _same(a, b, cfg.numeric_tolerance):
            continue
        severity = _parameter_severity(key, None if a is _MISSING else a, None if b is _MISSING else b, cfg)
        if a is _MISSING:
            summary = f"{label}: {key} added ({_text(b)})"
        elif b is _MISSING:
            summary = f"{label}: {key} removed (was {_text(a)})"
        else:
            summary = f"{label}: {key} changed from {_text(a)} to {_text(b)}"
        confidence = mk.base
        if _is_number(a) and _is_number(b):
            confidence = _confidence(mk.base, abs(b - a), cfg.numeric_tolerance, cfg)
        out.append(mk.make(ChangeType.PARAMETER_CHANGED, key, a, b, severity, summary, confidence))
    return out


def _compare_pair(o: ElementData, n: ElementData, method: str, cfg: ChangeDetectionConfig) -> list[Change]:
    if o.fingerprint() == n.fingerprint() and o.guid == n.guid:
        return []
    base = cfg.guid_match_confidence if method == "guid" else cfg.tag_match_confidence
    mk = _Maker(n, method, base, {"old_guid": o.guid} if method == "tag" else None)
    label = _label(n)
    out: list[Change] = []

    if o.ifc_class != n.ifc_class:
        out.append(mk.make(ChangeType.CLASSIFICATION_CHANGED, "ifc_class", o.ifc_class, n.ifc_class, Severity.HIGH,
                           f"{label} changed class from {_short(o.ifc_class)} to {_short(n.ifc_class)}"))
    out += _geometry_changes(o, n, mk, cfg)
    for attr, severity in (("level", Severity.HIGH), ("room", Severity.MEDIUM)):
        a, b = getattr(o, attr), getattr(n, attr)
        if a != b:
            if a and b:
                summary = f"{label} moved from {attr} {a} to {attr} {b}"
            elif b:
                summary = f"{label} placed in {attr} {b}"
            else:
                summary = f"{label} removed from {attr} {a}"
            out.append(mk.make(ChangeType.SPATIAL_CHANGED, attr, a, b, severity, summary))
    if o.material != n.material:
        out.append(mk.make(ChangeType.PARAMETER_CHANGED, "material", o.material, n.material, Severity.HIGH,
                           f"{label}: material changed from {_text(o.material)} to {_text(n.material)}"))
    out += _parameter_changes(o, n, mk, cfg)
    for attr in ("name", "tag"):
        a, b = getattr(o, attr), getattr(n, attr)
        if a != b:
            out.append(mk.make(ChangeType.METADATA_CHANGED, attr, a, b, Severity.LOW,
                               f"{label}: {attr} changed from {_text(a)} to {_text(b)}"))
    if method == "tag":
        out.append(mk.make(
            ChangeType.METADATA_CHANGED, "guid", o.guid, n.guid, Severity.LOW,
            f"{label}: element id changed (matched by class and tag, not by id)"))
    return out


# ----------------------------------------------------------------------------- matching
def _match_by_tag(removed: list[ElementData], added: list[ElementData]):
    """Pairs a removed and an added element that share class and tag when each is unique on its side.
    This recovers elements whose ids were regenerated by a re-export."""
    old_groups: dict[tuple[str, str], list[ElementData]] = defaultdict(list)
    new_groups: dict[tuple[str, str], list[ElementData]] = defaultdict(list)
    for e in removed:
        if e.tag:
            old_groups[(e.ifc_class, e.tag)].append(e)
    for e in added:
        if e.tag:
            new_groups[(e.ifc_class, e.tag)].append(e)
    pairs, used_old, used_new = [], set(), set()
    for key in sorted(old_groups.keys() & new_groups.keys()):
        if len(old_groups[key]) == 1 and len(new_groups[key]) == 1:
            o, n = old_groups[key][0], new_groups[key][0]
            pairs.append((o, n))
            used_old.add(o.guid)
            used_new.add(n.guid)
    return (pairs, [e for e in removed if e.guid not in used_old], [e for e in added if e.guid not in used_new])


# ----------------------------------------------------------------------------- public API
def detect_changes(old: Iterable[ElementData], new: Iterable[ElementData],
                   config: ChangeDetectionConfig = DEFAULT_CONFIG) -> list[Change]:
    old_by, new_by = {e.guid: e for e in old}, {e.guid: e for e in new}
    removed = [e for g, e in old_by.items() if g not in new_by]
    added = [e for g, e in new_by.items() if g not in old_by]
    pairs, removed, added = _match_by_tag(removed, added)

    changes: list[Change] = []
    for guid in old_by.keys() & new_by.keys():
        changes += _compare_pair(old_by[guid], new_by[guid], "guid", config)
    for o, n in pairs:
        changes += _compare_pair(o, n, "tag", config)

    ambiguous_classes = {e.ifc_class for e in removed} & {e.ifc_class for e in added}
    for kind, elements in ((ChangeType.ELEMENT_REMOVED, removed), (ChangeType.ELEMENT_ADDED, added)):
        for e in elements:
            severity = Severity.MEDIUM
            if e.ifc_class in config.high_impact_add_remove_classes or _is_load_bearing(e):
                severity = Severity.HIGH
            confidence = (config.ambiguous_add_remove_confidence if e.ifc_class in ambiguous_classes
                          else config.unambiguous_add_remove_confidence)
            where = f" in room {e.room}" if e.room else (f" on level {e.level}" if e.level else "")
            verb = "removed" if kind == ChangeType.ELEMENT_REMOVED else "added"
            changes.append(Change(
                change_type=kind, element_guid=e.guid, element_tag=e.tag, element_name=e.name,
                ifc_class=e.ifc_class, field="element",
                old_value=e.guid if kind == ChangeType.ELEMENT_REMOVED else None,
                new_value=e.guid if kind == ChangeType.ELEMENT_ADDED else None,
                severity=severity, confidence=confidence, summary=f"{_label(e)} {verb}{where}",
                match_method="none", detail={"ambiguous": e.ifc_class in ambiguous_classes},
            ))
    return _sorted(changes)


def detect_revision_metadata_changes(old: RevisionMeta, new: RevisionMeta,
                                     config: ChangeDetectionConfig = DEFAULT_CONFIG) -> list[Change]:
    out: list[Change] = []

    def make(field_name: str, a: Any, b: Any, severity: Severity, summary: str) -> Change:
        return Change(ChangeType.METADATA_CHANGED, None, "", "", "", field_name, a, b, severity,
                      config.guid_match_confidence, summary, "none")

    if old.model_schema != new.model_schema:
        out.append(make("model_schema", old.model_schema, new.model_schema, Severity.MEDIUM,
                        f"Model schema changed from {_text(old.model_schema)} to {_text(new.model_schema)}"))
    # A superseded status is set automatically when a newer revision arrives, so it is not a real change.
    if old.status != new.status and old.status != "superseded":
        severity = Severity.MEDIUM if new.status in ("issued", "rejected") else Severity.LOW
        out.append(make("status", old.status, new.status, severity,
                        f"Revision status changed from {old.status.replace('_', ' ')} to {new.status.replace('_', ' ')}"))
    return out


def _sorted(changes: list[Change]) -> list[Change]:
    return sorted(changes, key=lambda c: (c.element_guid is None, c.element_tag, c.element_guid or "",
                                          _TYPE_ORDER[c.change_type], c.field))
