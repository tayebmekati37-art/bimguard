import json

import pytest

from tests.conftest import upload

WALL_FOOTPRINT = {"x0": 0.0, "y0": -100.0, "x1": 8000.0, "y1": 100.0, "height": 4000.0}


def el(guid, cls, tag, location=None, rotation=0.0, footprint=None, dims=None, props=None):
    geometry = {}
    if location:
        geometry = {"location": location, "rotation_deg": rotation}
        if footprint:
            geometry["footprint"] = footprint
        if dims:
            geometry["dimensions"] = dims
    return {"id": guid, "class": cls, "tag": tag, "name": f"{cls} {tag}", "level": "L02", "room": None,
            "properties": props or {}, "geometry": geometry}


def model(*elements):
    return json.dumps({"elements": list(elements)}).encode()


def wall(x, tag="W-204", guid="w204", y=0.0):
    return el(guid, "IfcWall", tag, [x, y, 4500.0], 90.0, WALL_FOOTPRINT, {"Length": 8000.0, "Width": 200.0},
              {"Pset_WallCommon.LoadBearing": False})


def architecture(x=10000.0, extra=()):
    return model(wall(x), *extra)


SIDE_MODELS = {
    "S-201": model(el("c1", "IfcColumn", "C-B1", [10000.0, 0.0, 4500.0],
                      footprint={"x0": -200.0, "y0": -200.0, "x1": 200.0, "y1": 200.0, "height": 4000.0})),
    "M-301": model(el("ahu", "IfcUnitaryEquipment", "AHU-301", [11800.0, 1000.0, 4500.0],
                      footprint={"x0": -1200.0, "y0": -750.0, "x1": 1200.0, "y1": 750.0, "height": 2200.0})),
    "Q-101": model(el("q1", "QuantityItem", "QTO-WALL-AREA", props={"BasedOn": ["W-204", "W-101"], "Quantity": 80.0}),
                   el("q2", "QuantityItem", "QTO-OTHER", props={"BasedOn": ["W-9"], "Quantity": 5.0})),
    "E-020": model(el("cmp", "Equipment", "CMP-020", [27000.0, 3000.0, 4500.0],
                      dims={"Length": 2600.0, "Width": 1400.0})),
}


def api_doc(client, auth, project, number, discipline):
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": number, "name": f"{number} drawing", "discipline": discipline})
    assert r.status_code == 201, r.text
    return r.json()


def revise(client, auth, doc, content, revision, status="approved", name="m.json"):
    r = upload(client, auth("engineer"), doc["id"], content=content, filename=name,
               revision_number=str(revision), status=status)
    assert r.status_code == 201, r.text


def link(client, auth, source, target, kind="depends_on", confidence=1.0):
    r = client.post("/dependencies", headers=auth("engineer"), json={
        "source_document_id": source["id"], "target_document_id": target["id"], "relationship_type": kind,
        "confidence": confidence, "reason": f"{source['document_number']} follows {target['document_number']}"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def factory(client, auth, project):
    """Factory Expansion: A-101 v1, four dependents at v1, dependencies registered, then A-101 v2 arrives."""
    docs = {n: api_doc(client, auth, project, n, d) for n, d in (
        ("A-101", "architecture"), ("S-201", "structure"), ("M-301", "mep"), ("Q-101", "quantity"),
        ("E-020", "equipment"))}
    revise(client, auth, docs["A-101"], architecture(), 1)
    for number, content in SIDE_MODELS.items():
        revise(client, auth, docs[number], content, 1)
    deps = {
        "S-201": link(client, auth, docs["S-201"], docs["A-101"], "depends_on", 0.95),
        "M-301": link(client, auth, docs["M-301"], docs["A-101"], "depends_on", 0.9),
        "Q-101": link(client, auth, docs["Q-101"], docs["A-101"], "quantity_based_on", 1.0),
        "E-020": link(client, auth, docs["E-020"], docs["M-301"], "depends_on", 0.8),
    }
    revise(client, auth, docs["A-101"], architecture(10300.0, [wall(25000.0, "W-207", "w207", 0.0)]), 2, name="v2.json")
    return docs, deps


def impact(client, auth, project, role="viewer", query=""):
    r = client.get(f"/projects/{project['id']}/impact-analysis{query}", headers=auth(role))
    assert r.status_code == 200, r.text
    return r.json()


def by_number(result):
    return {e["impacted_document_number"]: e for e in result["events"]["items"]}


def test_a_new_revision_is_scored_automatically(client, auth, project, factory):
    result = impact(client, auth, project)
    assert [e["impacted_document_number"] for e in result["events"]["items"]] == ["S-201", "Q-101", "M-301", "E-020"]
    ev = by_number(result)
    assert ev["S-201"]["score"] == pytest.approx(56.9, abs=0.05) and ev["S-201"]["severity"] == "HIGH"
    assert ev["Q-101"]["score"] == pytest.approx(53.9, abs=0.05) and ev["Q-101"]["severity"] == "HIGH"
    assert ev["M-301"]["score"] == pytest.approx(48.7, abs=0.05) and ev["M-301"]["severity"] == "MEDIUM"
    assert ev["E-020"]["score"] == pytest.approx(23.9, abs=0.05) and ev["E-020"]["severity"] == "LOW"
    assert [(e["direct"], e["distance"]) for e in (ev["S-201"], ev["E-020"])] == [(True, 1), (False, 2)]
    assert result["counts"] == {"total": 4, "open": 4, "reviewed": 0, "advisory": 0,
                                "open_by_severity": {"HIGH": 2, "MEDIUM": 1, "LOW": 1}}
    (analysis,) = result["analyses"]
    assert analysis["changed_document_number"] == "A-101" and analysis["changed_revision_number"] == 2
    assert analysis["summary"] == {"total": 4, "by_severity": {"HIGH": 2, "MEDIUM": 1, "LOW": 1}, "changes": 2, "radius": 2}
    assert analysis["config"]["propagation_decay"] == 0.7


def test_every_score_is_explained(client, auth, project, factory):
    s = by_number(impact(client, auth, project))["S-201"]
    assert s["formula"] == "100 x 0.95 x 0.63 x 1.00 x 0.95 = 56.9"
    assert [f["key"] for f in s["factors"]] == ["dependency", "change", "propagation", "status"]
    assert all(f["explanation"] for f in s["factors"])
    assert "S-201 depends on A-101" in s["reason"] and "S-201 follows A-101" in s["reason"]
    assert s["path"][0]["from_number"] == "A-101" and s["path"][0]["to_number"] == "S-201"
    assert s["confidence"] == pytest.approx(0.94, abs=0.01)
    e = by_number(impact(client, auth, project))["E-020"]
    assert [p["to_number"] for p in e["path"]] == ["M-301", "E-020"] and "2 steps away" in e["factors"][2]["explanation"]


def test_affected_elements_are_found_deterministically(client, auth, project, factory):
    ev = by_number(impact(client, auth, project))
    column = ev["S-201"]["affected_elements"][0]
    assert column["tag"] == "C-B1" and column["kinds"] == ["proximity"] and column["distance_mm"] == 0
    assert "Overlaps or touches Wall W-204" in column["reasons"][0]
    ahu = ev["M-301"]["affected_elements"][0]
    assert ahu["tag"] == "AHU-301" and ahu["distance_mm"] == pytest.approx(200.0)
    assert ahu["reasons"] == ["200 mm from Wall W-204 after the change"]
    qto = ev["Q-101"]["affected_elements"]
    assert [q["tag"] for q in qto] == ["QTO-WALL-AREA"] and qto[0]["kinds"] == ["references"]
    assert ev["Q-101"]["affected_element_count"] == 1
    cmp_ = ev["E-020"]["affected_elements"][0]
    assert cmp_["tag"] == "CMP-020" and cmp_["distance_mm"] == pytest.approx(600.0)


def test_reviewing_a_dependency_resolves_its_impact(client, auth, project, factory):
    _, deps = factory
    h = auth("reviewer")
    assert client.post(f"/dependencies/{deps['S-201']['id']}/validate", headers=h).status_code == 200
    result = impact(client, auth, project)
    ev = by_number(result)
    assert ev["S-201"]["state"] == "reviewed" and ev["S-201"]["dependency_validated_against"] == 2
    assert ev["S-201"]["validated_by_name"] == "Reviewer"
    assert result["counts"]["open"] == 3 and result["counts"]["reviewed"] == 1
    assert impact(client, auth, project, query="?state=open")["events"]["total"] == 3
    # E-020 is reached through M-301, so it stays open until M-301 has been reviewed
    assert ev["E-020"]["state"] == "open"
    client.post(f"/dependencies/{deps['M-301']['id']}/validate", headers=h)
    ev = by_number(impact(client, auth, project))
    assert ev["M-301"]["state"] == "reviewed" and ev["E-020"]["state"] == "reviewed"
    assert impact(client, auth, project)["counts"]["open_by_severity"] == {"HIGH": 1}


def test_filters_and_pagination(client, auth, project, factory):
    assert impact(client, auth, project, query="?severity=high")["events"]["total"] == 2
    assert impact(client, auth, project, query="?severity=LOW")["events"]["items"][0]["impacted_document_number"] == "E-020"
    docs, _ = factory
    assert impact(client, auth, project, query=f"?document_id={docs['M-301']['id']}")["events"]["total"] == 1
    page = impact(client, auth, project, query="?limit=2&offset=1")["events"]
    assert page["total"] == 4 and [e["impacted_document_number"] for e in page["items"]] == ["Q-101", "M-301"]
    assert client.get(f"/projects/{project['id']}/impact-analysis?severity=extreme", headers=auth("viewer")).status_code == 422
    assert client.get(f"/projects/{project['id']}/impact-analysis?state=maybe", headers=auth("viewer")).status_code == 422


def test_changing_the_graph_updates_the_analysis(client, auth, project, factory):
    docs, deps = factory
    h = auth("engineer")
    assert client.delete(f"/dependencies/{deps['S-201']['id']}", headers=h).status_code == 204
    assert "S-201" not in by_number(impact(client, auth, project))
    again = link(client, auth, docs["S-201"], docs["A-101"], "depends_on", 0.95)
    ev = by_number(impact(client, auth, project))
    assert ev["S-201"]["score"] == pytest.approx(56.9, abs=0.05)
    assert ev["S-201"]["state"] == "reviewed"  # a dependency registered today is consistent with v2
    r = client.patch(f"/dependencies/{again['id']}", headers=h, json={"confidence": 0.5})
    assert r.status_code == 200
    updated = by_number(impact(client, auth, project))["S-201"]
    assert updated["score"] == pytest.approx(29.9, abs=0.05) and updated["severity"] == "MEDIUM"


def test_only_the_latest_revision_counts(client, auth, project, factory):
    docs, deps = factory
    assert client.post(f"/dependencies/{deps['S-201']['id']}/validate", headers=auth("reviewer")).status_code == 200
    assert by_number(impact(client, auth, project))["S-201"]["state"] == "reviewed"
    revise(client, auth, docs["A-101"], architecture(10400.0), 3, name="v3.json")
    result = impact(client, auth, project)
    assert [a["changed_revision_number"] for a in result["analyses"]] == [3]
    assert {e["changed_revision_number"] for e in result["events"]["items"]} == {3}
    # the review covered v2; v3 is new information, so the impact is open again
    assert by_number(result)["S-201"]["state"] == "open"


def test_run_endpoint_permissions_and_event_detail(client, auth, project, factory):
    assert client.post(f"/projects/{project['id']}/impact-analysis", headers=auth("viewer")).status_code == 403
    r = client.post(f"/projects/{project['id']}/impact-analysis", headers=auth("reviewer"))
    assert r.status_code == 200 and r.json()["counts"]["total"] == 4
    event_id = by_number(impact(client, auth, project))["M-301"]["id"]
    detail = client.get(f"/impact-events/{event_id}", headers=auth("viewer"))
    assert detail.status_code == 200 and detail.json()["impacted_document_number"] == "M-301"
    assert client.get("/impact-events/nope", headers=auth("viewer")).status_code == 404
    actions = {i["action"] for i in client.get(f"/audit-logs?project_id={project['id']}&limit=200",
                                                 headers=auth("admin")).json()["items"]}
    assert "impact.analyzed" in actions


def test_notes_explain_when_element_analysis_is_not_possible(client, auth, project):
    a = api_doc(client, auth, project, "A-101", "architecture")
    empty = api_doc(client, auth, project, "G-1", "general")
    pdf = api_doc(client, auth, project, "G-2", "general")
    revise(client, auth, a, architecture(), 1)
    revise(client, auth, pdf, b"%PDF-1.4 spec", 1, name="spec.pdf")
    link(client, auth, empty, a)
    link(client, auth, pdf, a)
    revise(client, auth, a, architecture(10300.0), 2, name="v2.json")
    ev = by_number(impact(client, auth, project))
    assert ev["G-1"]["note"] == "Element-level analysis unavailable: the document has no revisions."
    assert ev["G-2"]["note"] == "Element-level analysis unavailable: the current revision has no readable model data."
    assert ev["G-1"]["affected_elements"] == [] and ev["G-1"]["score"] > 0


def test_nothing_to_report_without_comparisons(client, auth, project):
    result = impact(client, auth, project)
    assert result["analyses"] == [] and result["events"]["total"] == 0
    assert result["counts"] == {"total": 0, "open": 0, "reviewed": 0, "advisory": 0, "open_by_severity": {}}


def test_unrelated_documents_are_not_affected(client, auth, project):
    a = api_doc(client, auth, project, "A-101", "architecture")
    lone = api_doc(client, auth, project, "X-900", "general")
    revise(client, auth, a, architecture(), 1)
    revise(client, auth, lone, SIDE_MODELS["Q-101"], 1)
    revise(client, auth, a, architecture(10300.0), 2, name="v2.json")
    assert impact(client, auth, project)["events"]["total"] == 0


def test_deleting_a_project_removes_impact_data(client, auth, project, factory, session_factory):
    from sqlalchemy import func, select

    from app.models.impact import ImpactAnalysis, ImpactEvent
    assert client.delete(f"/projects/{project['id']}", headers=auth("admin")).status_code == 204
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ImpactEvent)) == 0
        assert db.scalar(select(func.count()).select_from(ImpactAnalysis)) == 0
