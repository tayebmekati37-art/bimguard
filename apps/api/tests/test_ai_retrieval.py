import pytest

from app.ai.retrieval import build_facts_for_project
from app.ai.router import QuestionType
from app.models.dependency import Dependency


def _make_doc(client, auth, project_id, number, name, discipline):
    r = client.post(
        f"/projects/{project_id}/documents",
        headers=auth("engineer"),
        json={"document_number": number, "name": name, "discipline": discipline},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_empty_project_returns_no_facts(client, auth, project, session_factory):
    with session_factory() as db:
        facts = build_facts_for_project(db, project["id"], QuestionType.SUMMARY)
    assert facts == []


def test_dependency_becomes_fact(client, auth, project, session_factory):
    a = _make_doc(client, auth, project["id"], "A-101", "Level 2 Floor Plan", "architecture")
    s = _make_doc(client, auth, project["id"], "S-201", "Roof Framing", "structure")

    with session_factory() as db:
        db.add(Dependency(
            project_id=project["id"],
            source_document_id=s["id"],
            target_document_id=a["id"],
            relationship_type="depends_on",
            confidence=1.0,
            reason="test setup",
        ))
        db.commit()

    with session_factory() as db:
        facts = build_facts_for_project(db, project["id"], QuestionType.DEPENDENCIES)

    assert len(facts) == 1
    f = facts[0]
    assert f.kind == "dependency"
    assert "A-101" in f.identifiers
    assert "S-201" in f.identifiers
    assert "A-101" in f.text and "S-201" in f.text


def test_focus_document_filters_dependencies(client, auth, project, session_factory):
    a = _make_doc(client, auth, project["id"], "A-101", "Floor Plan", "architecture")
    s = _make_doc(client, auth, project["id"], "S-201", "Roof", "structure")
    m = _make_doc(client, auth, project["id"], "M-301", "HVAC", "mep")

    with session_factory() as db:
        db.add(Dependency(
            project_id=project["id"],
            source_document_id=s["id"], target_document_id=a["id"],
            relationship_type="depends_on", confidence=1.0, reason="r1",
        ))
        db.add(Dependency(
            project_id=project["id"],
            source_document_id=m["id"], target_document_id=a["id"],
            relationship_type="depends_on", confidence=1.0, reason="r2",
        ))
        db.commit()

    with session_factory() as db:
        facts = build_facts_for_project(
            db, project["id"], QuestionType.DEPENDENCIES, document_number="A-101"
        )

    assert len(facts) == 2
    all_text = " ".join(f.text for f in facts)
    assert "A-101" in all_text
    assert "S-201" in all_text
    assert "M-301" in all_text


def test_unknown_document_returns_no_facts(client, auth, project, session_factory):
    with session_factory() as db:
        facts = build_facts_for_project(
            db, project["id"], QuestionType.STATUS, document_number="ZZ-999"
        )
    assert facts == []