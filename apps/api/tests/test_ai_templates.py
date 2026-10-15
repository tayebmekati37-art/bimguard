from app.ai.facts import Fact
from app.ai.router import QuestionType
from app.ai.templates import render


def _f(text, kind, ids=None):
    return Fact(text=text, kind=kind, identifiers=ids or [])


def test_status_with_facts():
    facts = [_f("A-101 is Warning because v13 is in review.", "change", ["A-101", "v13"])]
    out = render(QuestionType.STATUS, facts, {"document_number": "A-101"})
    assert "A-101" in out
    assert "Warning" in out


def test_status_no_facts():
    out = render(QuestionType.STATUS, [], {"document_number": "A-101"})
    assert "No status information" in out


def test_validation_with_issues():
    facts = [_f("S-201 has validation issue: missing fire rating.", "validation", ["S-201"])]
    out = render(QuestionType.VALIDATION, facts, {"document_number": "S-201"})
    assert "S-201" in out
    assert "missing fire rating" in out


def test_validation_none():
    out = render(QuestionType.VALIDATION, [], {"document_number": "S-201"})
    assert "No validation issues" in out


def test_dependencies_with_edges():
    facts = [_f("A-101 depends on S-201.", "dependency", ["A-101", "S-201"])]
    out = render(QuestionType.DEPENDENCIES, facts, {"document_number": "A-101"})
    assert "A-101 depends on S-201." in out


def test_dependencies_none():
    out = render(QuestionType.DEPENDENCIES, [], {"document_number": "A-101"})
    assert "No dependencies" in out


def test_affected_by_with_edges():
    facts = [_f("S-201 depends on A-101.", "dependency", ["S-201", "A-101"])]
    out = render(QuestionType.AFFECTED_BY, facts, {"document_number": "A-101"})
    assert "S-201 depends on A-101." in out


def test_affects_with_edges():
    facts = [_f("S-201 depends on A-101.", "dependency", ["S-201", "A-101"])]
    out = render(QuestionType.AFFECTS, facts, {"document_number": "A-101"})
    assert "S-201 depends on A-101." in out


def test_summary_groups_by_kind():
    facts = [
        _f("A-101 changed.", "change", ["A-101"]),
        _f("S-201 depends on A-101.", "dependency", ["S-201", "A-101"]),
    ]
    out = render(QuestionType.SUMMARY, facts, {"document_number": "A-101"})
    assert "Summary for A-101" in out
    assert "change:" in out
    assert "dependency:" in out


def test_summary_empty():
    out = render(QuestionType.SUMMARY, [], {"document_number": "A-101"})
    assert "No information available" in out


def test_unknown_type_returns_help():
    out = render(QuestionType.UNKNOWN, [], {})
    assert "rephrase" in out.lower()


def test_deterministic_same_input_same_output():
    facts = [_f("A-101 changed.", "change", ["A-101"])]
    a = render(QuestionType.STATUS, facts, {"document_number": "A-101"})
    b = render(QuestionType.STATUS, facts, {"document_number": "A-101"})
    assert a == b


def test_renderer_does_not_invent_identifiers():
    facts = [_f("A-101 changed.", "change", ["A-101"])]
    out = render(QuestionType.STATUS, facts, {"document_number": "A-101"})
    assert "Z-999" not in out
    assert "S-201" not in out