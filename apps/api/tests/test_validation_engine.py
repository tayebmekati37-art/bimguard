import random
from dataclasses import replace

import pytest

from app.engines.graph import Edge, RelationshipType as R
from app.engines.validation import (
    AffectedRef, DocumentState, ElementReferences, OpenImpact, RevisionState, RuleConfig, Snapshot, assess,
    blocking_severity, default_configs, run_rules, validate_configuration, RULES,
)


def doc(id_, number, discipline, revision=1, status="approved", author="Demo", name=None, revisions=None, summary="Baseline"):
    revs = revisions if revisions is not None else (
        tuple(RevisionState(n, status if n == revision else "superseded", f"sum-{id_}-{n}", summary) for n in range(1, revision + 1))
        if revision else ())
    return DocumentState(id_, number, name or f"{number} drawing", discipline, status, author, "BIMGuard upload", revision, revs)


def edge(id_, source, target, kind=R.DEPENDS_ON, validated=None, confidence=1.0):
    return Edge(id=id_, source=source, target=target, relationship_type=kind, confidence=confidence,
                reason="test", validated_against_revision=validated)


def clean(**overrides):
    docs = (doc("A", "A-101", "architecture", 13), doc("S", "S-201", "structure", 8), doc("M", "M-301", "mep", 5),
            doc("Q", "Q-101", "quantity", 6), doc("E", "E-020", "equipment", 3))
    edges = (edge("e1", "S", "A", validated=13), edge("e2", "M", "A", validated=13),
             edge("e3", "Q", "A", R.QUANTITY_BASED_ON, validated=13), edge("e4", "E", "M", validated=5))
    return Snapshot(documents=docs, edges=edges, **overrides)


def only(rule_id, snapshot, **config):
    configs = default_configs()
    configs = {k: replace(v, enabled=(k == rule_id or k == "READINESS_POLICY")) for k, v in configs.items()}
    if config:
        configs[rule_id] = replace(configs[rule_id], **config)
    return run_rules(snapshot, configs)


def test_a_consistent_project_is_ready():
    findings = run_rules(clean())
    assert findings == []
    assert assess(findings, set(), "HIGH").status == "READY"


def test_default_rule_configurations_are_valid():
    for rule in RULES:
        validate_configuration(rule.id, rule.default_severity, rule.default_params)


def test_stale_dependency_names_the_revisions():
    snap = clean()
    snap = replace(snap, edges=tuple(replace(e, validated_against_revision=12) if e.id in ("e1", "e2", "e3") else e for e in snap.edges))
    snap = replace(snap, documents=tuple(replace(d, current_revision_number=13) if d.id == "A" else d for d in snap.documents))
    found = only("STALE_DEPENDENCY", snap)
    assert [f.document_number for f in found] == ["M-301", "Q-101", "S-201"]
    s = next(f for f in found if f.document_number == "S-201")
    assert s.severity == "HIGH"
    assert s.message == "S-201 (structure) was validated against A-101 v12, but A-101 is now v13."
    assert s.recommended_action.startswith("Review S-201 against A-101 v13")
    assert s.details == {"dependency_id": "e1", "provider": "A-101", "provider_current_revision": 13,
                         "validated_against_revision": 12, "relationship_type": "depends_on"}


def test_never_validated_and_two_way_relationships():
    snap = clean()
    snap = replace(snap, edges=(edge("x", "S", "A", validated=None), edge("y", "S", "M", R.SPATIALLY_RELATED_TO, validated=1)))
    found = only("STALE_DEPENDENCY", snap)
    assert len(found) == 1 and "no revision" in found[0].message  # two-way relationships are never stale


def test_revision_checks():
    snap = Snapshot(documents=(
        doc("A", "A-101", "architecture", revision=None),
        doc("B", "B-1", "general", revisions=(RevisionState(10, "superseded", "a"), RevisionState(13, "approved", "b")), revision=13),
        doc("C", "C-1", "general", revisions=(RevisionState(1, "superseded", "same"), RevisionState(2, "approved", "same")), revision=2),
    ))
    assert [f.document_number for f in only("MISSING_REVISION", snap)] == ["A-101"]
    gap = only("INVALID_REVISION_SEQUENCE", snap)
    assert [f.message for f in gap] == ["B-1 goes from v10 to v13, skipping 2 revision numbers."]
    assert only("INVALID_REVISION_SEQUENCE", snap, params={"max_gap": 3}) == []
    assert [f.document_number for f in only("DUPLICATE_REVISION_CONTENT", snap)] == ["C-1"]


def test_missing_dependency():
    docs = (doc("A", "A-101", "architecture"), doc("S", "S-201", "structure"), doc("M", "M-301", "mep"))
    snap = Snapshot(documents=docs, edges=(edge("e", "M", "A"),))
    found = only("MISSING_DEPENDENCY", snap)
    assert [f.document_number for f in found] == ["S-201"] and found[0].details == {"on_discipline": "architecture"}
    assert only("MISSING_DEPENDENCY", Snapshot(documents=docs[1:])) == []  # no architecture document in the project
    two_way = Snapshot(documents=docs, edges=(edge("e", "M", "A"), edge("f", "S", "A", R.SPATIALLY_RELATED_TO)))
    assert only("MISSING_DEPENDENCY", two_way) == []


def test_unresolved_references():
    refs = {"Q": (ElementReferences("QTO-1", ("W-1", "W-GONE")), ElementReferences("QTO-2", ("W-2", "W-GONE")))}
    snap = clean(references=refs, tags={"A": frozenset({"W-1", "W-2"})})
    (f,) = only("UNRESOLVED_REFERENCE", snap)
    assert f.document_number == "Q-101" and "2 references in Q-101" in f.message and "W-GONE" in f.message
    assert f.details["missing"][0] == {"element": "QTO-1", "reference": "W-GONE"}
    assert only("UNRESOLVED_REFERENCE", clean(references=refs, tags={"A": frozenset({"W-1", "W-2", "W-GONE"})})) == []
    assert only("UNRESOLVED_REFERENCE", clean(references=refs)) == []  # source model unreadable: no verdict


def impact(direct=False, severity="MEDIUM", score=35.9, doc_id="E", affected=(), first="M-301"):
    return OpenImpact("ev1", doc_id, "A-101", 13, direct, severity, score, first, tuple(affected))


def test_unreviewed_downstream_uses_impact_severity_for_indirect_impacts_only():
    snap = clean(open_impacts=(impact(), impact(direct=True, doc_id="S", score=60.9, severity="HIGH")))
    (f,) = only("UNREVIEWED_DOWNSTREAM", snap)
    assert f.document_number == "E-020" and f.severity == "MEDIUM"
    assert "indirectly by A-101 v13 (impact 35.9, medium)" in f.message
    assert "Review M-301 against A-101 v13 first" in f.recommended_action
    assert only("UNREVIEWED_DOWNSTREAM", snap, params={"min_score": 50.0, "use_impact_severity": True}) == []
    fixed = only("UNREVIEWED_DOWNSTREAM", snap, severity="LOW", params={"min_score": 0.0, "use_impact_severity": False})
    assert fixed[0].severity == "LOW"


def test_spatial_conflict_respects_the_clearance():
    close = AffectedRef("AHU-301", ("proximity", "same_room"), 200.0, ("200 mm from Wall W-204 after the change",))
    far = AffectedRef("DUCT", ("proximity",), 301.0, ("301 mm from Wall W-204 after the change",))
    room_only = AffectedRef("X", ("same_room",), None, ("In room 204, where W changed",))
    snap = clean(open_impacts=(impact(direct=True, doc_id="M", affected=(close, far, room_only)),))
    (f,) = only("SPATIAL_CONFLICT", snap)
    assert f.element_tag == "AHU-301" and f.severity == "HIGH" and f.details["distance_mm"] == 200.0
    assert f.message == "AHU-301 in M-301: 200 mm from Wall W-204 after the change. The required clearance is 300 mm."
    wider = only("SPATIAL_CONFLICT", snap, params={"clearance_mm": 400.0})
    assert len(wider) == 1 and wider[0].element_tag == "" and wider[0].message.startswith("2 elements in M-301")
    assert only("SPATIAL_CONFLICT", snap, params={"clearance_mm": 100.0}) == []


def test_many_close_elements_are_reported_once_per_document():
    elements = tuple(AffectedRef(f"B-{i}", ("proximity",), 0.0 if i < 3 else 200.0, ("x",)) for i in range(8))
    snap = clean(open_impacts=(impact(direct=True, doc_id="S", affected=elements),))
    (f,) = only("SPATIAL_CONFLICT", snap)
    assert f.document_number == "S-201" and f.title == "Potential spatial conflicts"
    assert f.message == ("8 elements in S-201 are within the required 300 mm clearance of elements that changed in A-101 v13: "
                         "B-0 (touching), B-1 (touching), B-2 (touching), B-3 (200 mm), B-4 (200 mm), B-5 (200 mm), and 2 more.")
    assert len(f.details["elements"]) == 8 and f.details["elements"][0] == {"element": "B-0", "distance_mm": 0.0}
    again = only("SPATIAL_CONFLICT", clean(open_impacts=(impact(direct=True, doc_id="S", affected=elements[:7]),)))
    assert again[0].fingerprint != f.fingerprint  # a different set of conflicts is a different finding


def test_outdated_reference():
    based = AffectedRef("QTO-WALL-AREA", ("references",), None, ("Based on Wall W-204",))
    other = AffectedRef("Z", ("same_room",), None, ())
    (f,) = only("OUTDATED_REFERENCE", clean(open_impacts=(impact(direct=True, doc_id="Q", affected=(based, other)),)))
    assert f.document_number == "Q-101" and "1 element in Q-101 (QTO-WALL-AREA)" in f.message and f.severity == "MEDIUM"


def test_parameter_mismatch():
    props = {"Q": {"QTO-ROOM-204-AREA": {"Quantity": 80.0}}, "A": {"204": {"Qto_SpaceBaseQuantities.NetFloorArea": 77.6}}}
    (f,) = only("PARAMETER_MISMATCH", clean(properties=props))
    assert f.document_number == "Q-101" and f.message == "Room 204 floor area: Q-101 says 80.0 but A-101 says 77.6."
    assert f.severity == "HIGH" and f.details["right"] == {"document": "A-101", "value": 77.6}
    ok = {"Q": {"QTO-ROOM-204-AREA": {"Quantity": 77.605}}, "A": props["A"]}
    assert only("PARAMETER_MISMATCH", clean(properties=ok)) == []                     # within tolerance 0.01
    assert only("PARAMETER_MISMATCH", clean(properties={"Q": props["Q"]})) == []      # nothing to compare against


def test_missing_metadata():
    snap = Snapshot(documents=(doc("A", "A-101", "architecture", author=" "), doc("S", "S-201", "structure", summary="")))
    assert [f.document_number for f in only("MISSING_METADATA", snap)] == ["A-101"]
    cfg = only("MISSING_METADATA", snap, params={"required_fields": ["author", "change_summary"]})
    assert sorted((f.document_number, f.details["field"]) for f in cfg) == [("A-101", "author"), ("S-201", "change_summary")]


def test_naming_convention():
    snap = Snapshot(documents=(doc("A", "A-101", "architecture"), doc("B", "A-1", "architecture"),
                               doc("C", "S-201", "architecture"), doc("D", "AX-301", "architecture")))
    found = {f.document_number: f.evidence for f in only("NAMING_CONVENTION", snap)}
    assert sorted(found) == ["A-1", "S-201"] and found["S-201"] == "S-201:architecture"
    custom = only("NAMING_CONVENTION", snap, params={"pattern": r"^[A-Z]-\d$", "check_prefix": False, "prefixes": {}})
    assert [f.document_number for f in custom] == ["A-101", "AX-301", "S-201"]


def test_approval_required():
    snap = Snapshot(documents=(doc("A", "A-101", "architecture", 13, status="in_review"), doc("S", "S-201", "structure", 8),
                               doc("N", "N-1", "general", revision=None)))
    (f,) = only("APPROVAL_REQUIRED", snap)
    assert f.document_number == "A-101" and f.message == "A-101 v13 is in review; it needs to be approved or issued before issue."
    assert only("APPROVAL_REQUIRED", snap, params={"required_status": ["in_review", "approved", "issued"]}) == []


def test_disabled_rules_are_silent_and_severity_is_configurable():
    snap = clean(); snap = replace(snap, documents=tuple(replace(d, author="") for d in snap.documents))
    assert len(only("MISSING_METADATA", snap)) == 5
    configs = default_configs()
    configs["MISSING_METADATA"] = replace(configs["MISSING_METADATA"], enabled=False)
    assert [f for f in run_rules(snap, configs) if f.rule_id == "MISSING_METADATA"] == []
    assert {f.severity for f in only("MISSING_METADATA", snap, severity="CRITICAL")} == {"CRITICAL"}


def test_readiness_levels_and_acknowledgement():
    snap = clean(); docs = tuple(replace(d, author="") if d.id in ("A", "S") else d for d in snap.documents)
    snap = replace(snap, documents=docs)
    warn = only("MISSING_METADATA", snap)                                  # two MEDIUM issues
    r = assess(warn, set(), "HIGH")
    assert (r.status, r.open_count, r.blocking_count, r.open_by_severity) == ("READY_WITH_WARNINGS", 2, 0, {"MEDIUM": 2})
    assert assess(warn, set(), "MEDIUM").status == "BLOCKED"
    ack = {f.fingerprint for f in warn}
    r = assess(warn, ack, "MEDIUM")
    assert (r.status, r.acknowledged_count) == ("READY", 2)
    critical = only("MISSING_METADATA", snap, severity="CRITICAL")
    r = assess(critical, {f.fingerprint for f in critical}, "HIGH")
    assert r.status == "BLOCKED" and r.acknowledged_count == 0 and r.open_by_severity == {"CRITICAL": 2}  # never acknowledgeable


def test_blocking_policy_is_configurable():
    configs = default_configs()
    assert blocking_severity(configs) == "HIGH"
    configs["READINESS_POLICY"] = replace(configs["READINESS_POLICY"], params={"blocking_severity": "CRITICAL"})
    assert blocking_severity(configs) == "CRITICAL"


def test_fingerprints_follow_the_evidence():
    stale = lambda rev: replace(clean(), edges=(edge("e1", "S", "A", validated=1),), documents=tuple(  # noqa: E731
        replace(d, current_revision_number=rev) if d.id == "A" else d for d in clean().documents))
    a, b, c = (only("STALE_DEPENDENCY", stale(r))[0] for r in (13, 13, 14))
    assert a.fingerprint == b.fingerprint != c.fingerprint
    assert len(a.fingerprint) == 32


def test_output_is_ordered_and_deterministic():
    docs = tuple(doc(f"D{i}", f"A-{100 + i}", "architecture", revision=None) for i in range(10))
    expected = run_rules(Snapshot(documents=docs))
    for seed in range(3):
        shuffled = list(docs)
        random.Random(seed).shuffle(shuffled)
        assert run_rules(Snapshot(documents=tuple(shuffled))) == expected
    severities = [f.severity for f in run_rules(clean(open_impacts=(impact(),)))]
    assert severities == sorted(severities, key=lambda s: -("LOW MEDIUM HIGH CRITICAL".split().index(s)))


def test_configuration_validation_gives_clear_messages():
    with pytest.raises(ValueError, match="Unknown rule"):
        validate_configuration("NOPE", None, None)
    with pytest.raises(ValueError, match="Severity must be one of"):
        validate_configuration("STALE_DEPENDENCY", "SEVERE", None)
    with pytest.raises(ValueError, match="Unknown parameter"):
        validate_configuration("STALE_DEPENDENCY", None, {"x": 1})
    with pytest.raises(ValueError, match="'clearance_mm' must be a number"):
        validate_configuration("SPATIAL_CONFLICT", None, {"clearance_mm": -1})
    with pytest.raises(ValueError, match="not a valid regular expression"):
        validate_configuration("NAMING_CONVENTION", None, {"pattern": "([", "check_prefix": True, "prefixes": {}})
    with pytest.raises(ValueError, match="'blocking_severity' must be one of"):
        validate_configuration("READINESS_POLICY", None, {"blocking_severity": "NONE"})
    with pytest.raises(ValueError, match="needs 'discipline' and 'on_discipline'"):
        validate_configuration("MISSING_DEPENDENCY", None, {"required": [{"discipline": "structure"}]})
    with pytest.raises(ValueError, match="'required_fields' must be a list"):
        validate_configuration("MISSING_METADATA", None, {"required_fields": ["colour"]})
    validate_configuration("SPATIAL_CONFLICT", "HIGH", {"clearance_mm": 450})
