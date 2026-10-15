from app.ai.facts import Fact
from app.ai.grounding import GroundingResult, check


def _facts(*ids, kind="change"):
    return [Fact(text="dummy", kind=kind, identifiers=list(ids))]


def test_empty_reply_is_ok():
    r = check("", _facts("A-101"))
    assert r.ok
    assert r.violations == []


def test_reply_with_only_known_ids_is_ok():
    r = check("A-101 depends on S-201.", _facts("A-101", "S-201"))
    assert r.ok, r.violations
    assert r.violations == []


def test_hallucinated_doc_number():
    r = check("A-101 depends on X-999.", _facts("A-101", "S-201"))
    assert not r.ok
    assert len(r.violations) == 1
    assert "X-999" in r.violations[0]


def test_hallucinated_revision():
    r = check("A-101 is at v14.", _facts("A-101", "revision v13"))
    assert not r.ok
    assert any("v14" in v for v in r.violations)


def test_known_revision_fragment_passes():
    r = check("A-101 is at v13.", _facts("A-101", "revision v13"))
    assert r.ok, r.violations


def test_hallucinated_element_tag():
    r = check("Wall W-999 moved.", _facts("A-101", "W-204"))
    assert not r.ok
    assert any("W-999" in v for v in r.violations)


def test_hallucinated_link():
    r = check("See https://example.com/x for details.", _facts("A-101"))
    assert not r.ok
    assert any("example.com" in v for v in r.violations)


def test_repeated_hallucination_one_violation():
    r = check("X-999 and X-999 again.", _facts("A-101"))
    assert len(r.violations) == 1


def test_reply_with_no_identifiers_is_ok():
    r = check("Everything looks fine.", _facts("A-101"))
    assert r.ok


def test_case_insensitive():
    r = check("a-101 depends on s-201.", _facts("A-101", "S-201"))
    assert r.ok, r.violations