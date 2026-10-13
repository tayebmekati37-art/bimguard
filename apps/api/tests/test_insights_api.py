from datetime import UTC, datetime, timedelta

import pytest

from tests.test_impact_api import api_doc, el, factory, link, model, revise  # noqa: F401
from tests.test_validation_api import validate  # noqa: F401


def health(client, auth, project):
    r = client.get(f"/projects/{project['id']}/health", headers=auth("viewer"))
    assert r.status_code == 200, r.text
    return r.json()


def states(h):
    return {d["document_number"]: d["state"] for d in h["documents_health"]}


def test_health_answers_what_is_the_state_of_my_project(client, auth, project, factory):
    h = health(client, auth, project)
    assert (h["documents"], h["documents_with_revision"], h["dependencies"], h["stale_dependencies"]) == (5, 5, 4, 3)
    assert h["disciplines"] == {"architecture": 1, "structure": 1, "mep": 1, "quantity": 1, "equipment": 1}
    assert h["open_impacts"] == {"total": 4, "by_severity": {"HIGH": 2, "MEDIUM": 1, "LOW": 1}}
    assert states(h) == {"A-101": "healthy", "E-020": "warning", "M-301": "stale", "Q-101": "critical", "S-201": "critical"}
    assert h["document_health"] == {"critical": 2, "stale": 1, "warning": 1, "healthy": 1}
    assert h["validation"] is None and h["project_name"] == project["name"]
    reasons = {d["document_number"]: d["reasons"] for d in h["documents_health"]}
    assert reasons["S-201"][0] == "Depends on A-101, now v2 (reviewed against v1)"
    assert any(r.startswith("Open impact from A-101 v2: high") for r in reasons["S-201"])
    assert reasons["A-101"] == [] and reasons["E-020"] == ["Open impact from A-101 v2: low (23.9)"]
    actions = [a["action"] for a in h["recent_activity"]]
    assert actions[0] == "impact.analyzed" and "revision.compared" in actions and "revision.created" in actions
    assert h["recent_activity"][0]["text"] == "A-101 v2: impact reaches 4 documents"


def test_health_recovers_as_dependencies_are_reviewed(client, auth, project, factory):
    _, deps = factory
    for dep in deps.values():
        client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer"))
    h = health(client, auth, project)
    assert h["stale_dependencies"] == 0 and h["open_impacts"]["total"] == 0
    assert set(states(h).values()) == {"healthy"}


def test_documents_that_are_not_approved_or_empty_are_warnings(client, auth, project):
    empty = api_doc(client, auth, project, "A-101", "architecture")
    pending = api_doc(client, auth, project, "A-102", "architecture")
    revise(client, auth, pending, model(el("x", "IfcWall", "W-1")), 1, status="in_review")
    h = health(client, auth, project)
    assert states(h) == {"A-101": "warning", "A-102": "warning"} and empty["id"]
    reasons = {d["document_number"]: d["reasons"] for d in h["documents_health"]}
    assert reasons["A-101"] == ["No revision uploaded"] and reasons["A-102"] == ["Current revision v1 is in review"]


def test_validation_status_and_outdated_flag(client, auth, project, factory):
    docs, deps = factory
    run = validate(client, auth, project)
    v = health(client, auth, project)["validation"]
    assert v["run_id"] == run["id"] and v["status"] == "BLOCKED" and v["outdated"] is False
    assert v["blocking"] == 5 and v["open_by_severity"] == {"HIGH": 5, "MEDIUM": 2}
    client.post(f"/dependencies/{deps['S-201']['id']}/validate", headers=auth("reviewer"))
    assert health(client, auth, project)["validation"]["outdated"] is True  # the data changed after the run
    assert validate(client, auth, project) and health(client, auth, project)["validation"]["outdated"] is False
    client.patch("/rules/SPATIAL_CONFLICT", headers=auth("admin"), json={"severity": "LOW"})
    assert health(client, auth, project)["validation"]["outdated"] is True  # so did the rules


def test_graph_nodes_carry_health_for_colouring(client, auth, project, factory):
    graph = client.get(f"/projects/{project['id']}/graph", headers=auth("viewer")).json()
    nodes = {n["document_number"]: n for n in graph["nodes"]}
    assert {k: v["health"] for k, v in nodes.items()} == {"A-101": "healthy", "E-020": "warning", "M-301": "stale",
                                                         "Q-101": "critical", "S-201": "critical"}
    assert nodes["M-301"]["health_reasons"][0].startswith("Depends on A-101, now v2")


def test_document_overview_for_the_graph_side_panel(client, auth, project, factory):
    docs, _ = factory
    s = client.get(f"/documents/{docs['S-201']['id']}/overview", headers=auth("viewer")).json()
    assert s["document"]["document_number"] == "S-201" and s["document"]["discipline"] == "structure"
    assert s["health_state"] == "critical" and s["downstream_count"] == 0 and s["radius"] == 0
    assert [(p["document_number"], p["relationship_type"], p["stale"]) for p in s["providers"]] == [("A-101", "depends_on", True)]
    assert s["dependents"] == [] and s["latest_comparison"] is None
    assert [(i["changed_document_number"], i["severity"], i["direct"]) for i in s["open_impacts"]] == [("A-101", "HIGH", True)]

    a = client.get(f"/documents/{docs['A-101']['id']}/overview", headers=auth("viewer")).json()
    assert a["health_state"] == "healthy" and a["downstream_count"] == 4 and a["radius"] == 2
    assert sorted(d["document_number"] for d in a["dependents"]) == ["M-301", "Q-101", "S-201"] and a["providers"] == []
    cmp_ = a["latest_comparison"]
    assert (cmp_["from_revision_number"], cmp_["to_revision_number"], cmp_["total_changes"]) == (1, 2, 2)
    assert cmp_["by_type"] == {"GEOMETRY_CHANGED": 1, "ELEMENT_ADDED": 1}
    assert client.get("/documents/nope/overview", headers=auth("viewer")).status_code == 404


def test_dashboard_summarises_every_active_project(client, auth, project, factory):
    quiet = client.post("/projects", json={"name": "Warehouse B"}, headers=auth("admin")).json()
    old = client.post("/projects", json={"name": "Old job"}, headers=auth("admin")).json()
    client.patch(f"/projects/{old['id']}", json={"status": "archived"}, headers=auth("admin"))
    validate(client, auth, project)
    d = client.get("/dashboard", headers=auth("viewer")).json()
    assert {p["project_name"] for p in d["projects"]} == {project["name"], "Warehouse B"}
    assert d["totals"] == {"projects": 2, "documents": 5, "stale_dependencies": 3, "open_impacts": 4, "blocked": 1,
                           "ready": 0, "not_validated": 1, "critical_documents": 2}
    mine = next(p for p in d["projects"] if p["project_id"] == project["id"])
    assert mine["validation"]["status"] == "BLOCKED" and mine["document_health"]["critical"] == 2
    assert next(p for p in d["projects"] if p["project_id"] == quiet["id"])["validation"] is None
    assert len(client.get("/dashboard?include_archived=true", headers=auth("viewer")).json()["projects"]) == 3


def search(client, auth, q):
    r = client.get(f"/search?q={q}", headers=auth("viewer"))
    assert r.status_code == 200, r.text
    return r.json()


def test_search_finds_projects_documents_elements_and_issues(client, auth, project, factory):
    validate(client, auth, project)
    assert [h["title"] for h in search(client, auth, "factory")["projects"]] == [project["name"]]
    docs = search(client, auth, "S-2")["documents"]
    assert [d["document_number"] for d in docs] == ["S-201"] and "Structure · v1 · approved" in docs[0]["subtitle"]
    assert [d["document_number"] for d in search(client, auth, "v2")["documents"]] == ["A-101"]       # by revision
    assert [d["document_number"] for d in search(client, auth, "structure")["documents"]] == ["S-201"]  # by discipline
    assert len(search(client, auth, "approved")["documents"]) == 5                                     # by status
    elements = search(client, auth, "W-204")["elements"]
    assert [e["title"] for e in elements][0].startswith("W-204") and elements[0]["document_number"] == "A-101"
    assert "in A-101 v2" in elements[0]["subtitle"]                                                    # current revision only
    assert search(client, auth, "AHU")["elements"][0]["document_number"] == "M-301"
    issues = search(client, auth, "outdated")["issues"]
    assert issues and all(i["kind"] == "issue" for i in issues)
    assert {i["document_number"] for i in search(client, auth, "stale")["issues"]} == {"M-301", "Q-101", "S-201"}
    empty = search(client, auth, "zzzzzz")
    assert (empty["projects"], empty["documents"], empty["elements"], empty["issues"]) == ([], [], [], [])


def test_search_validates_input_and_requires_sign_in(client, auth):
    assert client.get("/search?q=a", headers=auth("viewer")).status_code == 422
    assert client.get("/search?q=" + "x" * 101, headers=auth("viewer")).status_code == 422
    assert client.get("/search?q=abc").status_code == 401


def test_extra_document_filters(client, auth, project, factory):
    base = f"/projects/{project['id']}/documents"
    h = auth("viewer")
    assert client.get(base + "?file_type=json", headers=h).json()["total"] == 5
    assert client.get(base + "?file_type=.JSON", headers=h).json()["total"] == 5
    assert client.get(base + "?file_type=ifc", headers=h).json()["total"] == 0
    assert [d["document_number"] for d in client.get(base + "?revision=2", headers=h).json()["items"]] == ["A-101"]
    assert client.get(base + "?revision=9", headers=h).json()["total"] == 0
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    assert client.get(base + f"?modified_since={future}", headers=h).json()["total"] == 0
    assert client.get(base + f"?modified_since={past}", headers=h).json()["total"] == 5
    assert client.get(base + "?discipline=mep&revision=1", headers=h).json()["total"] == 1
