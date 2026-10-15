import pytest

from app.ai.provider import AIProviderError, ScriptedProvider
from app.api.ai import get_ai_provider
from app.main import app
from app.models.ai_query import AIQuery
from app.models.dependency import Dependency


def _make_doc(client, auth, project_id, number, name, discipline):
    r = client.post(
        f"/projects/{project_id}/documents",
        headers=auth("engineer"),
        json={"document_number": number, "name": name, "discipline": discipline},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _seed_dependency(client, auth, project, session_factory):
    a = _make_doc(client, auth, project["id"], "A-101", "Floor Plan", "architecture")
    s = _make_doc(client, auth, project["id"], "S-201", "Roof", "structure")
    with session_factory() as db:
        db.add(Dependency(
            project_id=project["id"],
            source_document_id=s["id"], target_document_id=a["id"],
            relationship_type="depends_on", confidence=1.0, reason="seed",
        ))
        db.commit()


def test_ask_requires_auth(client, project):
    r = client.post(f"/projects/{project['id']}/ask", json={"question": "what depends on A-101"})
    assert r.status_code == 401


def test_ask_unknown_project_404(client, auth):
    r = client.post(
        "/projects/does-not-exist/ask",
        headers=auth("engineer"),
        json={"question": "status of A-101"},
    )
    assert r.status_code == 404


def test_ask_empty_question_422(client, auth, project):
    r = client.post(
        f"/projects/{project['id']}/ask",
        headers=auth("engineer"),
        json={"question": ""},
    )
    assert r.status_code == 422


def test_ask_ai_off_returns_template(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)
    r = client.post(
        f"/projects/{project['id']}/ask",
        headers=auth("engineer"),
        json={"question": "what depends on A-101", "ai_enabled": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "template"
    assert body["question_type"] == "dependencies"
    assert "A-101" in body["answer"]
    assert body["violations"] == []

    with session_factory() as db:
        rows = list(db.query(AIQuery).all())
    assert len(rows) == 1
    assert rows[0].path == "template"


def test_ask_ai_on_valid_reply(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)
    app.dependency_overrides[get_ai_provider] = lambda: ScriptedProvider({"A-101": "S-201 depends on A-101."})

    r = client.post(
        f"/projects/{project['id']}/ask",
        headers=auth("engineer"),
        json={"question": "what depends on A-101", "ai_enabled": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "ai"
    assert body["answer"] == "S-201 depends on A-101."
    assert body["violations"] == []


def test_ask_ai_on_hallucination_falls_back(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)
    app.dependency_overrides[get_ai_provider] = lambda: ScriptedProvider({"A-101": "X-999 depends on A-101."})

    r = client.post(
        f"/projects/{project['id']}/ask",
        headers=auth("engineer"),
        json={"question": "what depends on A-101", "ai_enabled": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "template"
    assert any("X-999" in v for v in body["violations"])

def test_ai_status_disabled_by_default(client, auth):
    r = client.get("/ai/status", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is False
    assert body["model"] is None
    assert body["hourly_limit"] == 30


def test_ai_status_enabled_when_provider_configured(client, auth):
    app.dependency_overrides[get_ai_provider] = lambda: ScriptedProvider({})
    try:
        r = client.get("/ai/status", headers=auth("engineer"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is True
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)
