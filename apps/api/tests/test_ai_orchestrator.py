import asyncio

import pytest

from app.ai.orchestrator import Orchestrator
from app.ai.provider import AIProviderError, ScriptedProvider
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
    return a, s


def _run(coro):
    return asyncio.run(coro)


def test_ai_off_uses_template_and_logs(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)
    with session_factory() as db:
        orch = Orchestrator(db, provider=None, hourly_limit=10)
        result = _run(orch.answer(project["id"], "what depends on A-101", ai_enabled=False))
        assert result.path == "template"
        assert "A-101" in result.answer
        assert result.violations == []

    with session_factory() as db:
        rows = list(db.query(AIQuery).all())
    assert len(rows) == 1
    assert rows[0].path == "template"
    assert rows[0].question_type == "dependencies"


def test_ai_on_valid_reply_uses_ai_path(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)
    provider = ScriptedProvider({"A-101": "S-201 depends on A-101."})
    with session_factory() as db:
        orch = Orchestrator(db, provider=provider, hourly_limit=10)
        result = _run(orch.answer(project["id"], "what depends on A-101", ai_enabled=True))
        assert result.path == "ai"
        assert result.answer == "S-201 depends on A-101."
        assert result.violations == []

    with session_factory() as db:
        rows = list(db.query(AIQuery).all())
    assert len(rows) == 1
    assert rows[0].path == "ai"


def test_ai_on_hallucination_falls_back(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)
    provider = ScriptedProvider({"A-101": "X-999 depends on A-101."})
    with session_factory() as db:
        orch = Orchestrator(db, provider=provider, hourly_limit=10)
        result = _run(orch.answer(project["id"], "what depends on A-101", ai_enabled=True))
        assert result.path == "template"
        assert any("X-999" in v for v in result.violations)

    with session_factory() as db:
        rows = list(db.query(AIQuery).all())
    assert len(rows) == 1
    assert rows[0].path == "template"
    assert any("X-999" in v for v in rows[0].violations)


def test_ai_on_provider_error_falls_back(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)

    class BrokenProvider:
        async def complete(self, system, user):
            raise AIProviderError("boom")

    with session_factory() as db:
        orch = Orchestrator(db, provider=BrokenProvider(), hourly_limit=10)
        result = _run(orch.answer(project["id"], "what depends on A-101", ai_enabled=True))
        assert result.path == "template"


def test_hourly_limit_enforced(client, auth, project, session_factory):
    _seed_dependency(client, auth, project, session_factory)

    with session_factory() as db:
        for i in range(3):
            db.add(AIQuery(
                project_id=project["id"], question=f"q{i}", question_type="dependencies",
                answer="a", path="ai", facts=[], violations=[], model_name=None,
            ))
        db.commit()

    provider = ScriptedProvider({"A-101": "S-201 depends on A-101."})
    with session_factory() as db:
        orch = Orchestrator(db, provider=provider, hourly_limit=3)
        result = _run(orch.answer(project["id"], "what depends on A-101", ai_enabled=True))
        assert result.path == "template"

    with session_factory() as db:
        count_ai = db.query(AIQuery).filter(AIQuery.path == "ai").count()
    assert count_ai == 3