from dataclasses import replace

import pytest

from app.engines.graph import Edge, RelationshipType as R
from app.engines.validation import (
    BY_ID, DocumentState, ElementSummary, RevisionState, RuleConfig, Snapshot,
    default_configs, run_rules, validate_configuration,
)


# ------------------------------------------------------------------ helpers

def doc(id_, number, discipline, revision=1, status="approved"):
    revs = tuple(RevisionState(n, status if n == revision else "superseded", f"c-{id_}-{n}") for n in range(1, revision + 1))
    return DocumentState(id_, number, f"{number} drawing", discipline, status, "Demo", "BIMGuard upload", revision, revs)


def edge(id_, source, target, kind=R.DEPENDS_ON, validated=1):
    return Edge(id=id_, source=source, target=target, relationship_type=kind, confidence=1.0,
                reason="test", validated_against_revision=validated)


def elem(tag, level=None, room=None, material=None):
    return ElementSummary(tag=tag, level=level, room=room, material=material)


def elements(*items):
    return {e.tag: e for e in items}


def base_snapshot(**overrides):
    """S-201 depends on A-101, both with one shared tag. Override elements_by_document as needed."""
    docs = (doc("A", "A-101", "architecture", 13), doc("S", "S-201", "structure", 8))
    edges = (edge("e1", "S", "A", validated=13),)
    return Snapshot(documents=docs, edges=edges, **overrides)


def only(rule_id, snapshot, **config):
    configs = default_configs()
    configs = {k: replace(v, enabled=(k == rule_id or k == "READINESS_POLICY")) for k, v in configs.items()}
    if config:
        configs[rule_id] = replace(configs[rule_id], **config)
    return [f for f in run_rules(snapshot, configs) if f.rule_id == rule_id]


# ------------------------------------------------------------------ default validation

def test_default_configurations_of_new_rules_are_valid():
    for rid in ("CROSS_DOC_TAG_MISSING", "CROSS_DOC_PROPERTY_DIVERGENCE", "CROSS_DOC_TAG_UNEXPECTED"):
        rule = BY_ID[rid]
        validate_configuration(rid, rule.default_severity, rule.default_params)


def test_new_rules_are_registered():
    assert "CROSS_DOC_TAG_MISSING" in BY_ID
    assert "CROSS_DOC_PROPERTY_DIVERGENCE" in BY_ID
    assert "CROSS_DOC_TAG_UNEXPECTED" in BY_ID


def test_unexpected_rule_disabled_by_default():
    cfg = default_configs()["CROSS_DOC_TAG_UNEXPECTED"]
    assert cfg.enabled is False


def test_cross_doc_rules_categories():
    for rid in ("CROSS_DOC_TAG_MISSING", "CROSS_DOC_PROPERTY_DIVERGENCE", "CROSS_DOC_TAG_UNEXPECTED"):
        assert BY_ID[rid].category == "consistency"


# ------------------------------------------------------------------ CROSS_DOC_TAG_MISSING

def test_missing_tag_none_when_both_documents_empty():
    snap = base_snapshot()
    assert only("CROSS_DOC_TAG_MISSING", snap) == []


def test_missing_tag_none_when_all_tags_match():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2")),
        "S": elements(elem("W-204", level="L2")),
    })
    assert only("CROSS_DOC_TAG_MISSING", snap) == []


def test_missing_tag_emits_one_finding():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204"), elem("W-205")),
        "S": elements(elem("W-204")),
    })
    found = only("CROSS_DOC_TAG_MISSING", snap)
    assert len(found) == 1
    f = found[0]
    assert f.element_tag == "W-205"
    assert f.document_number == "S-201"  # finding on consumer
    assert "A-101" in f.message and "S-201" in f.message
    assert f.severity == "MEDIUM"
    assert f.details["provider"] == "A-101"
    assert f.details["consumer"] == "S-201"


def test_missing_tag_skips_when_consumer_has_no_elements():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204")),
        "S": {},   # explicit empty
    })
    assert only("CROSS_DOC_TAG_MISSING", snap) == []


def test_missing_tag_skips_when_provider_has_no_elements():
    snap = base_snapshot(elements_by_document={
        "A": {},
        "S": elements(elem("W-204")),
    })
    assert only("CROSS_DOC_TAG_MISSING", snap) == []


def test_missing_tag_respects_relationship_types():
    # edge is depends_on but rule narrowed to generated_from only
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204")),
        "S": elements(),
    })
    found = only("CROSS_DOC_TAG_MISSING", snap, params={"relationship_types": ["generated_from"]})
    assert found == []


def test_missing_tag_skips_two_way_edges():
    docs = (doc("A", "A-101", "architecture", 13), doc("M", "M-301", "mep", 5))
    edges = (edge("e1", "A", "M", kind=R.SPATIALLY_RELATED_TO, validated=1),)
    snap = Snapshot(documents=docs, edges=edges, elements_by_document={
        "A": elements(elem("W-204")),
        "M": elements(),
    })
    # provider is None on a two-way edge
    assert only("CROSS_DOC_TAG_MISSING", snap) == []


# ------------------------------------------------------------------ CROSS_DOC_TAG_UNEXPECTED

def test_unexpected_tag_default_off():
    """The rule is off in the shipped defaults, so run_rules on the raw default
    configs must not raise it. (The `only()` helper force-enables a rule, so it
    cannot be used here.)"""
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204")),
        "S": elements(elem("W-204"), elem("S-999")),
    })
    findings = run_rules(snap, default_configs())
    assert [f for f in findings if f.rule_id == "CROSS_DOC_TAG_UNEXPECTED"] == []


def test_unexpected_tag_when_enabled():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204")),
        "S": elements(elem("W-204"), elem("S-999")),
    })
    found = only("CROSS_DOC_TAG_UNEXPECTED", snap, enabled=True)
    assert len(found) == 1
    assert found[0].element_tag == "S-999"
    assert found[0].document_number == "S-201"
    assert found[0].severity == "LOW"


# ------------------------------------------------------------------ CROSS_DOC_PROPERTY_DIVERGENCE

def test_property_divergence_none_when_identical():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2", room="201", material="concrete")),
        "S": elements(elem("W-204", level="L2", room="201", material="concrete")),
    })
    assert only("CROSS_DOC_PROPERTY_DIVERGENCE", snap) == []


def test_property_divergence_level():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2")),
        "S": elements(elem("W-204", level="L3")),
    })
    found = only("CROSS_DOC_PROPERTY_DIVERGENCE", snap)
    assert len(found) == 1
    f = found[0]
    assert f.element_tag == "W-204"
    assert f.document_number == "S-201"
    assert "L2" in f.evidence and "L3" in f.evidence
    assert f.details["differences"][0]["field"] == "level"


def test_property_divergence_skips_when_one_side_is_none():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2", material="concrete")),
        "S": elements(elem("W-204", level=None, material="concrete")),
    })
    assert only("CROSS_DOC_PROPERTY_DIVERGENCE", snap) == []


def test_property_divergence_ignores_tag_present_in_one_side_only():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2")),
        "S": elements(elem("W-205", level="L3")),
    })
    assert only("CROSS_DOC_PROPERTY_DIVERGENCE", snap) == []


def test_property_divergence_compare_subset():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2", material="concrete")),
        "S": elements(elem("W-204", level="L3", material="concrete")),
    })
    found = only("CROSS_DOC_PROPERTY_DIVERGENCE", snap, params={
        "relationship_types": ["depends_on"], "compare": ["material"],
    })
    assert found == []


def test_property_divergence_multiple_fields_in_one_finding():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2", room="201", material="concrete")),
        "S": elements(elem("W-204", level="L3", room="202", material="concrete")),
    })
    found = only("CROSS_DOC_PROPERTY_DIVERGENCE", snap)
    assert len(found) == 1
    assert len(found[0].details["differences"]) == 2


def test_property_divergence_deterministic_fingerprint():
    snap = base_snapshot(elements_by_document={
        "A": elements(elem("W-204", level="L2")),
        "S": elements(elem("W-204", level="L3")),
    })
    a = only("CROSS_DOC_PROPERTY_DIVERGENCE", snap)
    b = only("CROSS_DOC_PROPERTY_DIVERGENCE", snap)
    assert [f.fingerprint for f in a] == [f.fingerprint for f in b]


# ------------------------------------------------------------------ wiring (through the real service)

def test_build_snapshot_populates_elements_by_document(client, auth, project, session_factory):
    """The real builder must fill elements_by_document from live BimElement rows."""
    from app.models.bim import BimElement
    from app.models.dependency import Dependency
    from app.models.document import Document, DocumentRevision
    from app.services import validation as v

    a = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "A-101", "name": "Arch", "discipline": "architecture"}).json()
    s = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "S-201", "name": "Struct", "discipline": "structure"}).json()

    with session_factory() as db:
        ra = DocumentRevision(document_id=a["id"], revision_number=1, file_path="x", original_filename="a.ifc",
                              file_size=1, checksum="aaa", created_by_name="test", status="approved",
                              extraction_status="ok", element_count=1)
        rs = DocumentRevision(document_id=s["id"], revision_number=1, file_path="x", original_filename="s.ifc",
                              file_size=1, checksum="bbb", created_by_name="test", status="approved",
                              extraction_status="ok", element_count=1)
        db.add_all([ra, rs])
        db.flush()
        db.add_all([
            BimElement(revision_id=ra.id, guid="g1", ifc_class="IfcWall", tag="W-204", level="L2",
                       room="201", material="concrete", fingerprint="f1"),
            BimElement(revision_id=rs.id, guid="g2", ifc_class="IfcWall", tag="W-999", level="L2",
                       room="201", material="concrete", fingerprint="f2"),
        ])
        db.add(Dependency(project_id=project["id"], source_document_id=s["id"], target_document_id=a["id"],
                          relationship_type="depends_on", confidence=1.0, reason="test", validated_against_revision=1))
        db.get(Document, a["id"]).current_revision_number = 1
        db.get(Document, s["id"]).current_revision_number = 1
        db.commit()

    with session_factory() as db:
        configs = v.rule_configs(db, project["id"])
        for rid in ("CROSS_DOC_TAG_MISSING", "CROSS_DOC_PROPERTY_DIVERGENCE"):
            configs[rid] = RuleConfig(rid, True, configs[rid].severity, configs[rid].params)
        snapshot = v.build_snapshot(db, project["id"], configs)
        assert a["id"] in snapshot.elements_by_document
        assert "W-204" in snapshot.elements_by_document[a["id"]]
        assert "W-999" in snapshot.elements_by_document[s["id"]]

        findings = run_rules(snapshot, configs)
        missing = [f for f in findings if f.rule_id == "CROSS_DOC_TAG_MISSING"]
        tags = {f.element_tag for f in missing}
        assert "W-204" in tags  # present in A, absent in S
        assert all(f.document_number == "S-201" for f in missing)