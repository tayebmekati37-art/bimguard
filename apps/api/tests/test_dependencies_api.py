import json

from tests.conftest import upload


def model(number, revision):
    return json.dumps({"elements": [{"id": f"{number}-{revision}", "class": "Item", "tag": number}]}).encode()


def make_doc(client, auth, project, number, discipline="general", revision=None):
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": number, "name": f"{number} drawing", "discipline": discipline})
    assert r.status_code == 201, r.text
    doc = r.json()
    if revision:
        new_revision(client, auth, doc, revision)
    return doc


def new_revision(client, auth, doc, revision):
    r = upload(client, auth("engineer"), doc["id"], content=model(doc["document_number"], revision),
               filename="m.json", revision_number=str(revision))
    assert r.status_code == 201, r.text


def link(client, auth, source, target, kind="depends_on", role="engineer", **extra):
    body = {"source_document_id": source["id"], "target_document_id": target["id"], "relationship_type": kind,
            "reason": "Test relationship", **extra}
    return client.post("/dependencies", headers=auth(role), json=body)


def test_dependency_is_directed_and_registered_as_current(client, auth, project):
    a101 = make_doc(client, auth, project, "A-101", "architecture", 12)
    s201 = make_doc(client, auth, project, "S-201", "structure", 8)
    r = link(client, auth, s201, a101, confidence=0.95)  # S-201 depends on A-101
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["flow"] == "target_to_source" and d["provider_number"] == "A-101"
    assert d["validated_against_revision"] == 12 and d["provider_current_revision"] == 12
    assert d["is_stale"] is False and d["strength"] == 0.95
    assert d["source_number"] == "S-201" and d["target_number"] == "A-101"
    affects = link(client, auth, a101, make_doc(client, auth, project, "M-301", "mep", 5), "affects").json()
    assert affects["provider_number"] == "A-101" and affects["flow"] == "source_to_target"
    assert affects["strength"] == 0.9


def test_validation_of_new_dependencies(client, auth, project):
    a, b = make_doc(client, auth, project, "A-101", revision=12), make_doc(client, auth, project, "S-201", revision=8)
    assert link(client, auth, b, a).status_code == 201
    dup = link(client, auth, b, a)
    assert dup.status_code == 409 and "already has" in dup.json()["detail"]
    assert link(client, auth, b, a, "references").status_code == 201  # a different type is a different relationship
    assert link(client, auth, a, a).status_code == 422
    assert link(client, auth, b, a, "teleports_to").status_code == 422
    assert link(client, auth, a, b, "affects", confidence=0).status_code == 422
    assert link(client, auth, a, b, "affects", confidence=1.5).status_code == 422
    short = client.post("/dependencies", headers=auth("engineer"), json={
        "source_document_id": a["id"], "target_document_id": b["id"], "relationship_type": "affects", "reason": "x"})
    assert short.status_code == 422
    assert link(client, auth, a, b, "affects", role="viewer").status_code == 403
    future = link(client, auth, b, a, "derived_from", validated_against_revision=99)
    assert future.status_code == 422 and "no revision v99" in future.json()["detail"]
    assert client.post("/dependencies", headers=auth("engineer"), json={
        "source_document_id": a["id"], "target_document_id": "nope", "relationship_type": "affects",
        "reason": "Test relationship"}).status_code == 404


def test_documents_must_share_a_project_and_project_must_be_active(client, auth, project):
    other = client.post("/projects", json={"name": "Other"}, headers=auth("admin")).json()
    a, b = make_doc(client, auth, project, "A-101", revision=1), make_doc(client, auth, other, "S-201", revision=1)
    r = link(client, auth, b, a)
    assert r.status_code == 422 and "same project" in r.json()["detail"]
    c = make_doc(client, auth, project, "S-301", revision=1)
    client.patch(f"/projects/{project['id']}", json={"status": "archived"}, headers=auth("admin"))
    assert link(client, auth, c, a).status_code == 409


def test_new_revision_makes_dependents_stale_and_validation_clears_it(client, auth, project):
    a101 = make_doc(client, auth, project, "A-101", "architecture", 12)
    s201 = make_doc(client, auth, project, "S-201", "structure", 8)
    dep = link(client, auth, s201, a101).json()
    new_revision(client, auth, a101, 13)

    stale = client.get(f"/dependencies/{dep['id']}", headers=auth("viewer")).json()
    assert stale["is_stale"] is True and stale["provider_current_revision"] == 13
    assert stale["validated_against_revision"] == 12

    assert client.post(f"/dependencies/{dep['id']}/validate", headers=auth("viewer")).status_code == 403
    too_high = client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer"), json={"revision_number": 14})
    assert too_high.status_code == 422
    still = client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer"), json={"revision_number": 12})
    assert still.json()["is_stale"] is True  # validated against an old revision does not clear staleness

    ok = client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer"))
    assert ok.status_code == 200
    body = ok.json()
    assert body["is_stale"] is False and body["validated_against_revision"] == 13
    assert body["validated_by_name"] == "Reviewer" and body["validated_at"] is not None

    items = client.get(f"/audit-logs?project_id={project['id']}&action=dependency.validated", headers=auth("admin")).json()["items"]
    assert items[0]["detail"] == {"provider": "A-101", "old_revision": 12, "new_revision": 13} or len(items) == 2


def test_dependency_on_a_document_without_revisions_becomes_stale_when_one_arrives(client, auth, project):
    a101, s201 = make_doc(client, auth, project, "A-101"), make_doc(client, auth, project, "S-201", revision=3)
    dep = link(client, auth, s201, a101).json()
    assert dep["validated_against_revision"] is None and dep["is_stale"] is False
    assert client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer")).status_code == 409
    new_revision(client, auth, a101, 1)
    assert client.get(f"/dependencies/{dep['id']}", headers=auth("viewer")).json()["is_stale"] is True


def test_spatial_relationships_are_symmetric_and_never_stale(client, auth, project):
    s, m = make_doc(client, auth, project, "S-201", revision=8), make_doc(client, auth, project, "M-301", revision=5)
    dep = link(client, auth, m, s, "spatially_related_to").json()
    assert dep["flow"] == "both" and dep["provider_document_id"] is None and dep["strength"] == 0.6
    new_revision(client, auth, s, 9)
    assert client.get(f"/dependencies/{dep['id']}", headers=auth("viewer")).json()["is_stale"] is False
    assert client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer")).status_code == 409
    assert [i["document_number"] for i in client.get(f"/documents/{s['id']}/impact", headers=auth("viewer")).json()["items"]] == ["M-301"]
    assert [i["document_number"] for i in client.get(f"/documents/{m['id']}/impact", headers=auth("viewer")).json()["items"]] == ["S-201"]


def test_listing_and_filters(client, auth, project):
    a, s, m = (make_doc(client, auth, project, n, revision=r) for n, r in (("A-101", 12), ("S-201", 8), ("M-301", 5)))
    link(client, auth, s, a)
    link(client, auth, m, a, "references")
    link(client, auth, m, s, "spatially_related_to")
    new_revision(client, auth, a, 13)
    base = f"/projects/{project['id']}/dependencies"
    h = auth("viewer")
    assert client.get(base, headers=h).json()["total"] == 3
    assert client.get(base + "?stale=true", headers=h).json()["total"] == 2
    assert client.get(base + "?stale=false", headers=h).json()["total"] == 1
    assert client.get(base + "?relationship_type=references", headers=h).json()["total"] == 1
    assert client.get(base + f"?document_id={s['id']}", headers=h).json()["total"] == 2
    assert client.get(base + "?limit=1&offset=2", headers=h).json()["items"].__len__() == 1


def test_update_and_delete(client, auth, project):
    a, s = make_doc(client, auth, project, "A-101", revision=1), make_doc(client, auth, project, "S-201", revision=1)
    dep = link(client, auth, s, a).json()
    r = client.patch(f"/dependencies/{dep['id']}", headers=auth("engineer"), json={"confidence": 0.5, "reason": "Revised reason"})
    assert r.status_code == 200 and r.json()["strength"] == 0.5 and r.json()["reason"] == "Revised reason"
    assert client.patch(f"/dependencies/{dep['id']}", headers=auth("viewer"), json={"confidence": 0.9}).status_code == 403
    assert client.delete(f"/dependencies/{dep['id']}", headers=auth("viewer")).status_code == 403
    assert client.delete(f"/dependencies/{dep['id']}", headers=auth("engineer")).status_code == 204
    assert client.get(f"/dependencies/{dep['id']}", headers=auth("viewer")).status_code == 404
    actions = {i["action"] for i in client.get(f"/audit-logs?project_id={project['id']}", headers=auth("admin")).json()["items"]}
    assert {"dependency.created", "dependency.updated", "dependency.deleted"} <= actions


def test_graph_endpoint_reports_nodes_edges_stale_and_cycles(client, auth, project):
    a, s = make_doc(client, auth, project, "A-101", "architecture", 12), make_doc(client, auth, project, "S-201", "structure", 8)
    link(client, auth, s, a)
    link(client, auth, a, s)  # mutual dependency: a cycle worth warning about
    g = client.get(f"/projects/{project['id']}/graph", headers=auth("viewer")).json()
    assert [n["document_number"] for n in g["nodes"]] == ["A-101", "S-201"]
    assert g["nodes"][0]["current_revision_number"] == 12 and len(g["edges"]) == 2
    assert g["cycles"] == [["A-101", "S-201"]] and g["stale_count"] == 0
    new_revision(client, auth, a, 13)
    assert client.get(f"/projects/{project['id']}/graph", headers=auth("viewer")).json()["stale_count"] == 1


def test_impact_traversal_direct_indirect_and_depth_limit(client, auth, project):
    a, s, e = (make_doc(client, auth, project, n, revision=1) for n in ("A-101", "S-201", "E-020"))
    link(client, auth, s, a)  # S-201 depends on A-101
    link(client, auth, e, s)  # E-020 depends on S-201
    h = auth("viewer")
    down = client.get(f"/documents/{a['id']}/impact", headers=h).json()
    assert down["radius"] == 2 and down["root_document_number"] == "A-101"
    assert [(i["document_number"], i["distance"], i["direct"]) for i in down["items"]] == [("S-201", 1, True), ("E-020", 2, False)]
    path = down["items"][1]["path"]
    assert [(p["from_number"], p["to_number"]) for p in path] == [("A-101", "S-201"), ("S-201", "E-020")]
    assert [i["document_number"] for i in client.get(f"/documents/{a['id']}/impact?max_depth=1", headers=h).json()["items"]] == ["S-201"]
    up = client.get(f"/documents/{e['id']}/impact?direction=upstream", headers=h).json()
    assert sorted(i["document_number"] for i in up["items"]) == ["A-101", "S-201"]
    assert client.get(f"/documents/{e['id']}/impact", headers=h).json()["items"] == []
    assert client.get(f"/documents/{a['id']}/impact?direction=sideways", headers=h).status_code == 422
    assert client.get("/documents/nope/impact", headers=h).status_code == 404


def test_cycles_do_not_hang_impact_analysis(client, auth, project):
    a, b, c = (make_doc(client, auth, project, n, revision=1) for n in ("A-1", "B-1", "C-1"))
    link(client, auth, b, a), link(client, auth, c, b), link(client, auth, a, c)
    items = client.get(f"/documents/{a['id']}/impact", headers=auth("viewer")).json()["items"]
    assert sorted(i["document_number"] for i in items) == ["B-1", "C-1"]


def test_factory_expansion_scenario(client, auth, project):
    docs = {n: make_doc(client, auth, project, n, d, r) for n, d, r in (
        ("A-101", "architecture", 12), ("S-201", "structure", 8), ("M-301", "mep", 5),
        ("Q-101", "quantity", 6), ("E-020", "equipment", 3))}
    link(client, auth, docs["S-201"], docs["A-101"], "depends_on", confidence=0.95)
    link(client, auth, docs["M-301"], docs["A-101"], "depends_on", confidence=0.9)
    link(client, auth, docs["Q-101"], docs["A-101"], "quantity_based_on", confidence=1.0)
    link(client, auth, docs["E-020"], docs["M-301"], "depends_on", confidence=0.8)
    link(client, auth, docs["M-301"], docs["S-201"], "spatially_related_to", confidence=0.6)
    base = f"/projects/{project['id']}/dependencies"
    assert client.get(base + "?stale=true", headers=auth("viewer")).json()["total"] == 0

    new_revision(client, auth, docs["A-101"], 13)  # the new architectural revision

    stale = client.get(base + "?stale=true", headers=auth("viewer")).json()["items"]
    assert sorted(d["source_number"] for d in stale) == ["M-301", "Q-101", "S-201"]
    assert all(d["provider_number"] == "A-101" and d["validated_against_revision"] == 12
               and d["provider_current_revision"] == 13 for d in stale)

    impact = client.get(f"/documents/{docs['A-101']['id']}/impact", headers=auth("viewer")).json()
    assert [(i["document_number"], i["distance"], i["strength"]) for i in impact["items"]] == [
        ("S-201", 1, 0.95), ("M-301", 1, 0.9), ("Q-101", 1, 0.9), ("E-020", 2, 0.72)]
    assert impact["radius"] == 2

    for dep in stale:  # the engineer reviews each dependent and records it
        assert client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer")).status_code == 200
    assert client.get(base + "?stale=true", headers=auth("viewer")).json()["total"] == 0


def test_deleting_a_project_removes_its_dependencies(client, auth, project, session_factory):
    from sqlalchemy import func, select

    from app.models.dependency import Dependency
    a, s = make_doc(client, auth, project, "A-101", revision=1), make_doc(client, auth, project, "S-201", revision=1)
    link(client, auth, s, a)
    assert client.delete(f"/projects/{project['id']}", headers=auth("admin")).status_code == 204
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Dependency)) == 0
