import re
from collections.abc import Callable
from typing import Any

from app.engines.graph import Edge, is_stale
from app.engines.validation.types import DocumentState, Finding, RuleConfig, Snapshot


class _Context:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.docs = {d.id: d for d in snapshot.documents}

    def number(self, doc_id: str) -> str:
        return self.docs[doc_id].number

    def current(self, doc_id: str) -> int | None:
        return self.docs[doc_id].current_revision_number

    def providers_of(self, doc_id: str) -> list[str]:
        """Documents whose changes can reach this one: its providers and its two-way neighbours."""
        found: list[str] = []
        for edge in self.snapshot.edges:
            if edge.consumer == doc_id and edge.provider:
                found.append(edge.provider)
            elif edge.provider is None and doc_id in (edge.source, edge.target):
                found.append(edge.target if edge.source == doc_id else edge.source)
        return sorted(set(found), key=lambda i: self.docs[i].number)


def _finding(rule: RuleConfig, doc: DocumentState | None, title: str, message: str, action: str, *, subject: str,
             evidence: str, severity: str | None = None, element_tag: str = "", details: dict[str, Any] | None = None) -> Finding:
    return Finding(rule_id=rule.rule_id, severity=severity or rule.severity, document_id=doc.id if doc else None,
                   document_number=doc.number if doc else "", title=title, message=message, recommended_action=action,
                   subject=subject, evidence=evidence, element_tag=element_tag, details=details or {})


def missing_revision(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    return [_finding(rule, d, "No revision", f"{d.number} has no revision, so there is nothing to issue.",
                     f"Upload the first revision of {d.number}.", subject="revision", evidence="none")
            for d in ctx.snapshot.documents if d.current_revision_number is None]


def invalid_revision_sequence(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    max_gap = rule.params.get("max_gap", 1)
    for d in ctx.snapshot.documents:
        numbers = sorted(r.number for r in d.revisions)
        for a, b in zip(numbers, numbers[1:]):
            if b - a > max_gap:
                out.append(_finding(
                    rule, d, "Revision numbers skip", f"{d.number} goes from v{a} to v{b}, skipping {b - a - 1} revision numbers.",
                    "Check that no revision is missing from the project, or explain the gap in the change summary.",
                    subject="sequence", evidence=f"{a}->{b}", details={"from": a, "to": b, "max_gap": max_gap}))
    return out


def duplicate_revision_content(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    for d in ctx.snapshot.documents:
        seen: dict[str, int] = {}
        for r in sorted(d.revisions, key=lambda r: r.number):
            if r.checksum and r.checksum in seen:
                out.append(_finding(rule, d, "Identical revisions", f"{d.number} v{r.number} has exactly the same content as v{seen[r.checksum]}.",
                                    "Remove the duplicate revision or upload the intended changes.",
                                    subject="duplicate", evidence=f"{seen[r.checksum]}={r.number}"))
            else:
                seen[r.checksum] = r.number
    return out


def stale_dependency(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    for edge in ctx.snapshot.edges:
        if edge.provider is None:
            continue
        current = ctx.current(edge.provider)
        if not is_stale(edge, current):
            continue
        consumer, provider = ctx.docs[edge.consumer], ctx.docs[edge.provider]
        validated = edge.validated_against_revision
        seen = f"v{validated}" if validated is not None else "no revision"
        out.append(_finding(
            rule, consumer, "Outdated dependency revision",
            f"{consumer.number} ({consumer.discipline}) was validated against {provider.number} {seen}, "
            f"but {provider.number} is now v{current}.",
            f"Review {consumer.number} against {provider.number} v{current}, update it if needed, "
            "then mark the dependency as reviewed.",
            subject=edge.id, evidence=f"{provider.number}@{current}",
            details={"dependency_id": edge.id, "provider": provider.number, "provider_current_revision": current,
                     "validated_against_revision": validated, "relationship_type": edge.relationship_type.value}))
    return out


def missing_dependency(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    by_discipline: dict[str, list[DocumentState]] = {}
    for d in ctx.snapshot.documents:
        by_discipline.setdefault(d.discipline, []).append(d)
    for requirement in rule.params.get("required", []):
        wanted = requirement["on_discipline"]
        for d in by_discipline.get(requirement["discipline"], []):
            candidates = [p for p in by_discipline.get(wanted, []) if p.id != d.id]
            if not candidates:
                continue
            if not any(ctx.docs[p].discipline == wanted for p in ctx.providers_of(d.id)):
                out.append(_finding(
                    rule, d, "Missing dependency", f"{d.number} ({d.discipline}) is not linked to any {wanted} document, "
                    f"so changes to {', '.join(c.number for c in candidates[:3])} would not reach it.",
                    f"Register the {wanted} document {d.number} depends on, or disable this check for this discipline.",
                    subject=wanted, evidence=wanted, details={"on_discipline": wanted}))
    return out


def unresolved_reference(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    for d in ctx.snapshot.documents:
        refs = ctx.snapshot.references.get(d.id)
        if not refs:
            continue
        providers = [p for p in ctx.providers_of(d.id) if p in ctx.snapshot.tags]
        if not providers:
            continue
        known: set[str] = set().union(*(ctx.snapshot.tags[p] for p in providers))
        missing = sorted({(e.tag, r) for e in refs for r in e.refs if r not in known})
        if missing:
            names = sorted({r for _, r in missing})
            out.append(_finding(
                rule, d, "Unresolved references",
                f"{len(missing)} {'reference' if len(missing) == 1 else 'references'} in {d.number} {'points' if len(missing) == 1 else 'point'} to elements that do not exist "
                f"in {', '.join(ctx.number(p) for p in providers)}: {', '.join(names[:8])}{f', and {len(names) - 8} more' if len(names) > 8 else ''}.",
                f"Update the affected elements of {d.number} or restore the missing elements in the source document.",
                subject="references", evidence=",".join(names),
                details={"missing": [{"element": t, "reference": r} for t, r in missing[:50]]}))
    return out


def unreviewed_downstream(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    for impact in ctx.snapshot.open_impacts:
        if impact.direct or impact.score < rule.params.get("min_score", 0):
            continue
        doc = ctx.docs[impact.impacted_document_id]
        severity = impact.severity if rule.params.get("use_impact_severity", True) else rule.severity
        out.append(_finding(
            rule, doc, "Downstream document not reviewed",
            f"{doc.number} is affected indirectly by {impact.changed_document_number} v{impact.changed_revision_number} "
            f"(impact {impact.score:.1f}, {impact.severity.lower()}) and has not been reviewed.",
            f"Review {impact.first_hop_number} against {impact.changed_document_number} v{impact.changed_revision_number} first, "
            f"then check {doc.number}.",
            subject=f"{impact.changed_document_number}->{doc.number}",
            evidence=f"{impact.changed_document_number}@{impact.changed_revision_number}", severity=severity,
            details={"impact_score": impact.score, "impact_severity": impact.severity, "via": impact.first_hop_number}))
    return out


def spatial_conflict(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    """One finding per impacted document: the elements within the clearance of a changed element."""
    out = []
    clearance = rule.params.get("clearance_mm", 300.0)
    for impact in ctx.snapshot.open_impacts:
        doc = ctx.docs[impact.impacted_document_id]
        close = sorted(((a.distance_mm, a) for a in impact.affected
                        if "proximity" in a.kinds and a.distance_mm is not None and a.distance_mm <= clearance),
                       key=lambda t: (t[0], t[1].tag))
        if not close:
            continue
        changed = f"{impact.changed_document_number} v{impact.changed_revision_number}"
        evidence_key = ",".join(f"{a.tag}:{d:.0f}" for d, a in close)
        details = {"clearance_mm": clearance, "elements": [{"element": a.tag, "distance_mm": d} for d, a in close]}
        if len(close) == 1:
            distance, a = close[0]
            what = next((r for r in a.reasons if "mm from" in r or r.startswith("Overlaps")), "is close to a changed element")
            out.append(_finding(
                rule, doc, "Potential spatial conflict", f"{a.tag} in {doc.number}: {what[0].lower() + what[1:]}. "
                f"The required clearance is {clearance:.0f} mm.",
                f"Check {a.tag} against the changed {changed} and move it or confirm the clearance.",
                subject=a.tag, evidence=f"{changed}:{evidence_key}", element_tag=a.tag,
                details={"distance_mm": distance, **details}))
            continue
        shown = ", ".join(f"{a.tag} ({'touching' if d == 0 else f'{d:.0f} mm'})" for d, a in close[:6])
        out.append(_finding(
            rule, doc, "Potential spatial conflicts",
            f"{len(close)} elements in {doc.number} are within the required {clearance:.0f} mm clearance of elements "
            f"that changed in {changed}: {shown}{f', and {len(close) - 6} more' if len(close) > 6 else ''}.",
            f"Check these elements of {doc.number} against {changed} and move them or confirm the clearance.",
            subject="spatial", evidence=f"{changed}:{evidence_key}", details=details))
    return out


def outdated_reference(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    for impact in ctx.snapshot.open_impacts:
        doc = ctx.docs[impact.impacted_document_id]
        based = [a.tag for a in impact.affected if "references" in a.kinds]
        if not based:
            continue
        out.append(_finding(
            rule, doc, "Information may be outdated",
            f"{len(based)} {'element' if len(based) == 1 else 'elements'} in {doc.number} "
            f"({', '.join(based[:6])}{f', and {len(based) - 6} more' if len(based) > 6 else ''}) {'is' if len(based) == 1 else 'are'} based on elements that changed in "
            f"{impact.changed_document_number} v{impact.changed_revision_number}.",
            f"Update {doc.number} from {impact.changed_document_number} v{impact.changed_revision_number}, upload the new revision, "
            "then mark the dependency as reviewed.",
            subject=f"{impact.changed_document_number}->{doc.number}",
            evidence=f"{impact.changed_document_number}@{impact.changed_revision_number}:{len(based)}",
            details={"elements": based[:50]}))
    return out


def parameter_mismatch(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []

    def values(side: dict) -> list[tuple[DocumentState, Any]]:
        found = []
        for d in ctx.snapshot.documents:
            if d.discipline == side["discipline"]:
                props = ctx.snapshot.properties.get(d.id, {}).get(side["tag"], {})
                if side["property"] in props:
                    found.append((d, props[side["property"]]))
        return found

    for check in rule.params.get("checks", []):
        for left_doc, left in values(check["left"]):
            for right_doc, right in values(check["right"]):
                numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (left, right))
                differs = abs(left - right) > check["tolerance"] if numeric else left != right
                if left_doc.id != right_doc.id and differs:
                    out.append(_finding(
                        rule, left_doc, f"{check['name']} does not match",
                        f"{check['name']}: {left_doc.number} says {left} but {right_doc.number} says {right}.",
                        f"Update {left_doc.number} or confirm the value in {right_doc.number}, then upload a new revision.",
                        subject=check["name"], evidence=f"{left}|{right}",
                        details={"left": {"document": left_doc.number, "value": left},
                                 "right": {"document": right_doc.number, "value": right}, "tolerance": check["tolerance"]}))
    return out


def missing_metadata(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    for d in ctx.snapshot.documents:
        current = next((r for r in d.revisions if r.number == d.current_revision_number), None)
        values = {"author": d.author, "name": d.name, "source_system": d.source_system,
                  "change_summary": current.change_summary if current else "x"}
        missing = [f for f in rule.params.get("required_fields", []) if not str(values.get(f) or "").strip()]
        for field_name in missing:
            out.append(_finding(rule, d, "Missing metadata", f"{d.number} has no {field_name.replace('_', ' ')}.",
                                f"Fill in the {field_name.replace('_', ' ')} of {d.number}.",
                                subject=field_name, evidence=field_name, details={"field": field_name}))
    return out


def naming_convention(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    pattern = re.compile(rule.params["pattern"])
    prefixes = rule.params.get("prefixes", {})
    for d in ctx.snapshot.documents:
        if not pattern.match(d.number):
            out.append(_finding(rule, d, "Naming convention", f"'{d.number}' does not match the pattern {rule.params['pattern']}.",
                                f"Rename {d.number} to follow the project's convention.", subject="pattern", evidence=d.number))
        elif rule.params.get("check_prefix") and d.discipline in prefixes and \
                not d.number.upper().startswith(prefixes[d.discipline] + "-") and \
                not re.match(rf"^{re.escape(prefixes[d.discipline])}[A-Z]?-", d.number):
            out.append(_finding(rule, d, "Naming convention",
                                f"{d.number} is a {d.discipline} document but does not start with '{prefixes[d.discipline]}'.",
                                f"Use the {prefixes[d.discipline]} prefix for {d.discipline} documents.",
                                subject="prefix", evidence=f"{d.number}:{d.discipline}"))
    return out


def approval_required(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out = []
    allowed = set(rule.params.get("required_status", []))
    for d in ctx.snapshot.documents:
        if d.current_revision_number is None:
            continue
        current = next((r for r in d.revisions if r.number == d.current_revision_number), None)
        status = current.status if current else d.status
        if status not in allowed:
            out.append(_finding(
                rule, d, "Revision not approved",
                f"{d.number} v{d.current_revision_number} is {status.replace('_', ' ')}; it needs to be "
                f"{' or '.join(sorted(allowed))} before issue.",
                f"Have a reviewer approve {d.number} v{d.current_revision_number}.",
                subject="approval", evidence=f"{d.current_revision_number}:{status}",
                details={"revision": d.current_revision_number, "status": status}))
    return out


CHECKS: dict[str, Callable[[_Context, RuleConfig], list[Finding]]] = {
    "MISSING_REVISION": missing_revision,
    "INVALID_REVISION_SEQUENCE": invalid_revision_sequence,
    "DUPLICATE_REVISION_CONTENT": duplicate_revision_content,
    "STALE_DEPENDENCY": stale_dependency,
    "MISSING_DEPENDENCY": missing_dependency,
    "UNRESOLVED_REFERENCE": unresolved_reference,
    "UNREVIEWED_DOWNSTREAM": unreviewed_downstream,
    "SPATIAL_CONFLICT": spatial_conflict,
    "OUTDATED_REFERENCE": outdated_reference,
    "PARAMETER_MISMATCH": parameter_mismatch,
    "MISSING_METADATA": missing_metadata,
    "NAMING_CONVENTION": naming_convention,
    "APPROVAL_REQUIRED": approval_required,
}

__all__ = ["CHECKS", "Edge"]


# ------------------------------------------------------------------ cross-document element checks
def _qualifying_pairs(ctx: _Context, rule: RuleConfig):
    """Yield (provider_doc, consumer_doc, provider_elements, consumer_elements, edge) for each edge
    whose relationship type is configured and whose both ends have extractable element data."""
    allowed = set(rule.params.get("relationship_types") or ())
    for edge in ctx.snapshot.edges:
        if edge.relationship_type.value not in allowed:
            continue
        provider_id, consumer_id = edge.provider, edge.consumer
        if provider_id is None or consumer_id is None:
            continue
        provider_elements = ctx.snapshot.elements_by_document.get(provider_id)
        consumer_elements = ctx.snapshot.elements_by_document.get(consumer_id)
        if not provider_elements or not consumer_elements:
            continue
        yield ctx.docs[provider_id], ctx.docs[consumer_id], provider_elements, consumer_elements, edge


def cross_doc_tag_missing(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out: list[Finding] = []
    for provider, consumer, provider_elems, consumer_elems, edge in _qualifying_pairs(ctx, rule):
        missing = sorted(set(provider_elems) - set(consumer_elems))
        for tag in missing:
            out.append(_finding(
                rule, consumer,
                "Element missing from dependent document",
                f"{tag} is in {provider.number} but not in {consumer.number}.",
                f"Add {tag} to {consumer.number} or remove it from {provider.number}, then re-upload the corrected document.",
                subject=f"{edge.id}|{tag}",
                evidence=f"{provider.number}:{tag}",
                element_tag=tag,
                details={"dependency_id": edge.id, "provider": provider.number, "consumer": consumer.number,
                         "relationship_type": edge.relationship_type.value}))
    return out


def cross_doc_tag_unexpected(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    out: list[Finding] = []
    for provider, consumer, provider_elems, consumer_elems, edge in _qualifying_pairs(ctx, rule):
        unexpected = sorted(set(consumer_elems) - set(provider_elems))
        for tag in unexpected:
            out.append(_finding(
                rule, consumer,
                "Element not present in provider document",
                f"{tag} is in {consumer.number} but not in {provider.number}.",
                f"Confirm {tag} is meant to exist in {consumer.number}, or add it to {provider.number}.",
                subject=f"{edge.id}|{tag}",
                evidence=f"{consumer.number}:{tag}",
                element_tag=tag,
                details={"dependency_id": edge.id, "provider": provider.number, "consumer": consumer.number,
                         "relationship_type": edge.relationship_type.value}))
    return out


def cross_doc_property_divergence(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    compare_fields = rule.params.get("compare") or ()
    out: list[Finding] = []
    for provider, consumer, provider_elems, consumer_elems, edge in _qualifying_pairs(ctx, rule):
        for tag in sorted(set(provider_elems) & set(consumer_elems)):
            p, c = provider_elems[tag], consumer_elems[tag]
            diffs: list[tuple[str, object, object]] = []
            for name in compare_fields:
                pv = getattr(p, name, None)
                cv = getattr(c, name, None)
                if pv is None or cv is None:
                    continue
                if pv != cv:
                    diffs.append((name, pv, cv))
            if not diffs:
                continue
            summary = "; ".join(f"{n}: {provider.number}={pv!r}, {consumer.number}={cv!r}" for n, pv, cv in diffs)
            evidence = "|".join(f"{n}={pv}/{cv}" for n, pv, cv in diffs)
            out.append(_finding(
                rule, consumer,
                "Element property disagrees across documents",
                f"{tag} differs between {provider.number} and {consumer.number}: {summary}.",
                f"Decide which value is correct, update the other document, then re-upload it.",
                subject=f"{edge.id}|{tag}",
                evidence=evidence,
                element_tag=tag,
                details={"dependency_id": edge.id, "provider": provider.number, "consumer": consumer.number,
                         "relationship_type": edge.relationship_type.value,
                         "differences": [{"field": n, "provider": pv, "consumer": cv} for n, pv, cv in diffs]}))
    return out

# ------------------------------------------------------------------ register cross-document checks
CHECKS["CROSS_DOC_TAG_MISSING"] = cross_doc_tag_missing
CHECKS["CROSS_DOC_TAG_UNEXPECTED"] = cross_doc_tag_unexpected
CHECKS["CROSS_DOC_PROPERTY_DIVERGENCE"] = cross_doc_property_divergence

# ------------------------------------------------------------------ manufacturing
def part_coverage(ctx: _Context, rule: RuleConfig) -> list[Finding]:
    """Every part (target of any 'part_of' edge) must be covered by at least one supporting document.

    Coverage means a document with a `specification_for`, `test_for`, or
    `work_instruction_for` relationship whose target is the part. Which
    relationship types count is configurable.
    """
    required = set(rule.params.get("required") or ())
    if not required:
        return []

    part_ids: set[str] = set()
    for edge in ctx.snapshot.edges:
        if edge.relationship_type.value == "part_of":
            part_ids.add(edge.source)

    covered_ids: set[str] = set()
    for edge in ctx.snapshot.edges:
        if edge.relationship_type.value in required:
            covered_ids.add(edge.target)

    missing = sorted(part_ids - covered_ids, key=lambda pid: ctx.docs[pid].number)
    out: list[Finding] = []
    for part_id in missing:
        doc = ctx.docs[part_id]
        out.append(_finding(
            rule, doc,
            "Part without supporting documents",
            f"{doc.number} is a part but has no specification, test, or work instruction "
            f"pointing at it.",
            f"Add a document with one of these relationships to {doc.number}: "
            f"{', '.join(sorted(required))}.",
            subject="part_coverage",
            evidence="|".join(sorted(required)),
            details={"part": doc.number, "required": sorted(required)}))
    return out


CHECKS["PART_COVERAGE"] = part_coverage