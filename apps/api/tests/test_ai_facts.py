from app.ai.facts import Fact, FactBuilder


def test_build_empty():
    assert FactBuilder().build({}) == []
    assert FactBuilder().build({"changes": [], "impacts": []}) == []


def test_from_change_basic():
    f = FactBuilder().from_change({
        "document_number": "A-101",
        "revision": "v13",
        "element_tag": "WALL-204",
        "field": "location",
        "old_value": "10.0",
        "new_value": "10.3",
    })
    assert f.kind == "change"
    assert "A-101" in f.text
    assert "v13" in f.text
    assert "WALL-204" in f.text
    assert "A-101" in f.identifiers
    assert "WALL-204" in f.identifiers


def test_from_dependency_has_two_identifiers():
    f = FactBuilder().from_dependency({
        "source": "A-101",
        "target": "S-201",
        "type": "depends on",
    })
    assert f.kind == "dependency"
    assert f.text == "A-101 depends on S-201."
    assert "A-101" in f.identifiers
    assert "S-201" in f.identifiers


def test_from_validation_with_revision():
    f = FactBuilder().from_validation({
        "document_number": "S-201",
        "revision": "v8",
        "message": "missing fire rating",
    })
    assert f.kind == "validation"
    assert "S-201" in f.identifiers
    assert any("v8" in i for i in f.identifiers)
    assert "missing fire rating" in f.text


def test_from_impact():
    f = FactBuilder().from_impact({
        "source": "A-101",
        "target": "M-301",
        "severity": "high",
    })
    assert f.kind == "impact"
    assert "M-301" in f.identifiers
    assert "A-101" in f.identifiers
    assert f.text.startswith("High impact")


def test_build_dedupes_identical_records():
    edge = {"source": "A-101", "target": "S-201", "type": "depends on"}
    facts = FactBuilder().build({"dependencies": [edge, dict(edge)]})
    assert len(facts) == 1


def test_build_mixed_input():
    facts = FactBuilder().build({
        "changes": [{"document_number": "A-101", "revision": "v13"}],
        "dependencies": [{"source": "A-101", "target": "S-201", "type": "depends on"}],
        "validation": [{"document_number": "S-201", "message": "stale"}],
        "impacts": [{"source": "A-101", "target": "M-301", "severity": "critical"}],
    })
    assert len(facts) == 4
    assert {f.kind for f in facts} == {"change", "dependency", "validation", "impact"}


def test_fact_is_frozen():
    f = Fact(text="x", kind="y", identifiers=[])
    try:
        f.text = "z"
    except Exception:
        return
    raise AssertionError("Fact should be frozen")