import pytest

from tests.conftest import upload  # noqa: F401
from tests.test_impact_api import api_doc, architecture, el, factory, link, model, revise  # noqa: F401


def validate(client, auth, project, role="reviewer"):
    r = client.post(f"/projects/{project['id']}/validate", headers=auth(role))
    assert r.status_code == 201, r.text
    return r.json()


def issues(client, auth, run, query=""):
    r = client.get(f"/validation-runs/{run['id']}/issues{query}", headers=auth("viewer"))
    assert r.status_code == 200, r.text
    return r.json()


def by_rule(page):
    out = {}
    for i in page["items"]:
        out.setdefault(i["rule_id"], []).append(i)
    return out


def set_rule(client, auth, rule_id, **body):
    r = client.patch(f"/rules/{rule_id}", headers=auth("admin"), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def review_all(client, auth, deps):
    for dep in deps.values():
        client.post(f"/dependencies/{dep['id']}/validate", headers=auth("reviewer"))


def test_blocked_with_specific_issues_then_ready_after_review_and_acknowledgement(client, auth, project, factory):
    docs, deps = factory
    run = validate(client, auth, project)
    assert run["status"] == "BLOCKED" and run["created_by_name"] == "Reviewer"
    s = run["summary"]
    assert (s["documents_checked"], s["total"], s["open"], s["blocking"]) == (5, 7, 7, 5)
    assert s["open_by_severity"] == {"HIGH": 5, "MEDIUM": 2} and s["blocking_severity"] == "HIGH"
    assert s["by_rule"] == {"STALE_DEPENDENCY": 3, "SPATIAL_CONFLICT": 2, "UNRESOLVED_REFERENCE": 1, "OUTDATED_REFERENCE": 1}

    page = issues(client, auth, run)
    rules = by_rule(page)
    assert [i["rule_id"] for i in (page["items"][0], page["items"][-1])] == ["SPATIAL_CONFLICT", "UNRESOLVED_REFERENCE"]
    stale = {i["document_number"]: i for i in rules["STALE_DEPENDENCY"]}
    assert sorted(stale) == ["M-301", "Q-101", "S-201"] and stale["S-201"]["severity"] == "HIGH"
    assert stale["S-201"]["message"] == "S-201 (structure) was validated against A-101 v1, but A-101 is now v2."
    assert stale["S-201"]["recommended_action"].startswith("Review S-201 against A-101 v2")
    assert stale["S-201"]["details"]["provider"] == "A-101" and stale["S-201"]["category"] == "dependency"
    spatial = {i["element_tag"]: i for i in rules["SPATIAL_CONFLICT"]}
    assert spatial["AHU-301"]["message"] == "AHU-301 in M-301: 200 mm from Wall W-204 after the change. The required clearance is 300 mm."
    assert spatial["C-B1"]["message"].startswith("C-B1 in S-201: overlaps or touches Wall W-204")
    assert rules["OUTDATED_REFERENCE"][0]["message"].startswith("1 element in Q-101 (QTO-WALL-AREA) is based on elements that changed in A-101 v2")
    assert rules["UNRESOLVED_REFERENCE"][0]["message"] == (
        "2 references in Q-101 point to elements that do not exist in A-101: W-101, W-9.")
    assert "UNREVIEWED_DOWNSTREAM" not in rules  # E-020's impact (23.9) is below the 25 threshold

    review_all(client, auth, deps)
    run2 = validate(client, auth, project)
    assert run2["status"] == "READY_WITH_WARNINGS" and run2["summary"]["total"] == 1 and run2["summary"]["blocking"] == 0
    (left,) = issues(client, auth, run2)["items"]
    assert left["rule_id"] == "UNRESOLVED_REFERENCE" and left["severity"] == "MEDIUM"

    r = client.post(f"/issues/{left['id']}/acknowledge", headers=auth("reviewer"),
                    json={"note": "W-101 and W-9 are legacy items removed from scope"})
    assert r.status_code == 200 and r.json()["status"] == "acknowledged" and r.json()["acknowledged_by_name"] == "Reviewer"
    now = client.get(f"/validation-runs/{run2['id']}", headers=auth("viewer")).json()
    assert now["status"] == "READY" and now["summary"]["acknowledged"] == 1 and now["summary"]["open"] == 0

    run3 = validate(client, auth, project)  # the accepted risk is remembered
    assert run3["status"] == "READY" and run3["summary"]["acknowledged"] == 1
    assert issues(client, auth, run3, "?status=acknowledged")["items"][0]["acknowledgement_note"].startswith("W-101")


def test_critical_issues_cannot_be_acknowledged_and_roles_are_enforced(client, auth, project, factory):
    set_rule(client, auth, "STALE_DEPENDENCY", severity="CRITICAL")
    run = validate(client, auth, project)
    critical = issues(client, auth, run, "?severity=critical")["items"][0]
    r = client.post(f"/issues/{critical['id']}/acknowledge", headers=auth("admin"), json={"note": "Accepting this anyway"})
    assert r.status_code == 409 and "Critical issues cannot be acknowledged" in r.json()["detail"]
    medium = issues(client, auth, run, "?severity=medium")["items"][0]
    note = {"note": "Reviewed with the project lead"}
    assert client.post(f"/issues/{medium['id']}/acknowledge", headers=auth("engineer"), json=note).status_code == 403
    assert client.post(f"/issues/{medium['id']}/acknowledge", headers=auth("viewer"), json=note).status_code == 403
    assert client.post(f"/issues/{medium['id']}/acknowledge", headers=auth("reviewer"), json={"note": "ok"}).status_code == 422
    assert client.post(f"/issues/{medium['id']}/acknowledge", headers=auth("bim_coordinator"), json=note).status_code == 200
    assert client.post(f"/issues/{medium['id']}/acknowledge", headers=auth("reviewer"), json=note).status_code == 409
    assert client.post("/issues/nope/acknowledge", headers=auth("reviewer"), json=note).status_code == 404

    revoked = client.delete(f"/issues/{medium['id']}/acknowledge", headers=auth("reviewer"))
    assert revoked.status_code == 200 and revoked.json()["status"] == "open" and revoked.json()["acknowledged_by_name"] == ""
    assert client.delete(f"/issues/{medium['id']}/acknowledge", headers=auth("reviewer")).status_code == 409
    assert validate(client, auth, project)["summary"]["acknowledged"] == 0


def test_an_acknowledgement_only_covers_the_evidence_it_was_given_for(client, auth, project, factory):
    docs, deps = factory
    review_all(client, auth, deps)
    run = validate(client, auth, project)
    (issue,) = issues(client, auth, run)["items"]
    client.post(f"/issues/{issue['id']}/acknowledge", headers=auth("reviewer"), json={"note": "Known legacy references"})
    assert validate(client, auth, project)["status"] == "READY"
    revise(client, auth, docs["Q-101"], model(el("q1", "QuantityItem", "QTO-WALL-AREA", props={"BasedOn": ["W-77"]})), 2, name="q2.json")
    again = validate(client, auth, project)
    assert again["status"] == "READY_WITH_WARNINGS" and again["summary"]["acknowledged"] == 0
    assert "W-77" in issues(client, auth, again)["items"][0]["message"]


def test_rules_are_listed_with_their_defaults(client, auth):
    rules = client.get("/rules", headers=auth("viewer")).json()
    assert len(rules) == 14 and rules[0]["rule_id"] == "MISSING_REVISION"
    assert all(r["is_default"] and r["enabled"] for r in rules)
    policy = next(r for r in rules if r["rule_id"] == "READINESS_POLICY")
    assert policy["params"] == {"blocking_severity": "HIGH"} and not policy["can_disable"] and not policy["configurable_severity"]
    stale = next(r for r in rules if r["rule_id"] == "STALE_DEPENDENCY")
    assert (stale["severity"], stale["category"], stale["default_severity"]) == ("HIGH", "dependency", "HIGH")


def test_rule_configuration_is_admin_only_validated_and_audited(client, auth, project):
    assert client.patch("/rules/STALE_DEPENDENCY", headers=auth("engineer"), json={"enabled": False}).status_code == 403
    assert client.patch("/rules/STALE_DEPENDENCY", headers=auth("bim_coordinator"), json={"enabled": False}).status_code == 403
    r = client.patch("/rules/SPATIAL_CONFLICT", headers=auth("admin"), json={"severity": "CRITICAL", "params": {"clearance_mm": 450}})
    assert r.status_code == 200 and r.json()["severity"] == "CRITICAL" and r.json()["params"] == {"clearance_mm": 450}
    assert r.json()["is_default"] is False and r.json()["updated_by_name"] == "Admin"
    bad = client.patch("/rules/SPATIAL_CONFLICT", headers=auth("admin"), json={"params": {"clearance_mm": -5}})
    assert bad.status_code == 422 and "'clearance_mm' must be a number" in bad.json()["detail"]
    assert client.patch("/rules/SPATIAL_CONFLICT", headers=auth("admin"), json={"severity": "SEVERE"}).status_code == 422
    assert client.patch("/rules/SPATIAL_CONFLICT", headers=auth("admin"), json={"params": {"nope": 1}}).status_code == 422
    assert client.patch("/rules/READINESS_POLICY", headers=auth("admin"), json={"enabled": False}).status_code == 422
    assert client.patch("/rules/READINESS_POLICY", headers=auth("admin"), json={"severity": "LOW"}).status_code == 422
    assert client.patch("/rules/NAMING_CONVENTION", headers=auth("admin"),
                        json={"params": {"pattern": "([", "check_prefix": True, "prefixes": {}}}).status_code == 422
    assert client.patch("/rules/NOPE", headers=auth("admin"), json={"enabled": False}).status_code == 404
    reset = client.post("/rules/SPATIAL_CONFLICT/reset", headers=auth("admin"))
    assert reset.status_code == 200 and reset.json()["is_default"] and reset.json()["severity"] == "HIGH"
    assert client.post("/rules/SPATIAL_CONFLICT/reset", headers=auth("reviewer")).status_code == 403
    actions = {i["action"] for i in client.get("/audit-logs?limit=100", headers=auth("admin")).json()["items"]}
    assert {"rule.updated", "rule.reset"} <= actions


def test_disabling_a_rule_removes_its_issues_and_the_policy_decides_what_blocks(client, auth, project, factory):
    set_rule(client, auth, "STALE_DEPENDENCY", enabled=False)
    run = validate(client, auth, project)
    assert "STALE_DEPENDENCY" not in run["summary"]["by_rule"] and run["rules_snapshot"]["STALE_DEPENDENCY"]["enabled"] is False
    assert run["status"] == "BLOCKED"  # the spatial conflicts still block
    set_rule(client, auth, "READINESS_POLICY", params={"blocking_severity": "CRITICAL"})
    relaxed = validate(client, auth, project)
    assert relaxed["status"] == "READY_WITH_WARNINGS" and relaxed["summary"]["blocking"] == 0 and relaxed["summary"]["open"] == 4
    set_rule(client, auth, "READINESS_POLICY", params={"blocking_severity": "MEDIUM"})
    assert validate(client, auth, project)["status"] == "BLOCKED"


def test_indirect_impacts_become_issues_when_the_threshold_allows(client, auth, project, factory):
    set_rule(client, auth, "UNREVIEWED_DOWNSTREAM", params={"min_score": 10.0, "use_impact_severity": True})
    page = issues(client, auth, validate(client, auth, project), "?rule_id=UNREVIEWED_DOWNSTREAM")
    (e,) = page["items"]
    assert e["document_number"] == "E-020" and e["severity"] == "LOW"
    assert e["message"] == "E-020 is affected indirectly by A-101 v2 (impact 23.9, low) and has not been reviewed."
    assert e["recommended_action"] == "Review M-301 against A-101 v2 first, then check E-020."


def test_shared_parameters_must_agree_across_documents(client, auth, project):
    a, q = api_doc(client, auth, project, "A-101", "architecture"), api_doc(client, auth, project, "Q-101", "quantity")
    space = lambda area: model(el("sp", "IfcSpace", "204", props={"Qto_SpaceBaseQuantities.NetFloorArea": area}))  # noqa: E731
    revise(client, auth, a, space(80.0), 1)
    revise(client, auth, q, model(el("qq", "QuantityItem", "QTO-ROOM-204-AREA", props={"Quantity": 80.0})), 1)
    link(client, auth, q, a, "quantity_based_on")
    assert "PARAMETER_MISMATCH" not in by_rule(issues(client, auth, validate(client, auth, project)))
    revise(client, auth, a, space(77.6), 2, name="a2.json")
    (m,) = by_rule(issues(client, auth, validate(client, auth, project)))["PARAMETER_MISMATCH"]
    assert m["document_number"] == "Q-101" and m["severity"] == "HIGH" and m["category"] == "consistency"
    assert m["message"] == "Room 204 floor area: Q-101 says 80.0 but A-101 says 77.6."
    assert m["details"]["right"] == {"document": "A-101", "value": 77.6}
    revise(client, auth, q, model(el("qq", "QuantityItem", "QTO-ROOM-204-AREA", props={"Quantity": 77.6})), 2, name="q2.json")
    assert "PARAMETER_MISMATCH" not in by_rule(issues(client, auth, validate(client, auth, project)))


def test_basic_document_checks(client, auth, project):
    bad = api_doc(client, auth, project, "BAD1", "architecture")
    pending = api_doc(client, auth, project, "A-102", "architecture")
    revise(client, auth, pending, model(el("x", "IfcWall", "W-1")), 1, status="in_review")
    assert client.patch(f"/documents/{pending['id']}", headers=auth("engineer"), json={"author": ""}).status_code == 200
    found = by_rule(issues(client, auth, validate(client, auth, project)))
    assert [i["document_number"] for i in found["MISSING_REVISION"]] == ["BAD1"] and found["MISSING_REVISION"][0]["severity"] == "HIGH"
    assert "does not match the pattern" in found["NAMING_CONVENTION"][0]["message"] and found["NAMING_CONVENTION"][0]["document_number"] == "BAD1"
    assert found["APPROVAL_REQUIRED"][0]["message"] == "A-102 v1 is in review; it needs to be approved or issued before issue."
    assert found["MISSING_METADATA"][0]["message"] == "A-102 has no author." and found["MISSING_METADATA"][0]["severity"] == "MEDIUM"
    assert bad["id"] and "MISSING_DEPENDENCY" not in found  # no structure/mep/quantity documents to be checked


def test_history_latest_filters_and_permissions(client, auth, project, factory):
    docs, _ = factory
    empty = client.post("/projects", json={"name": "Empty"}, headers=auth("admin")).json()
    assert client.get(f"/projects/{empty['id']}/validation-runs/latest", headers=auth("viewer")).status_code == 404
    assert client.post(f"/projects/{project['id']}/validate", headers=auth("viewer")).status_code == 403
    first, second = validate(client, auth, project, "engineer"), validate(client, auth, project)
    runs = client.get(f"/projects/{project['id']}/validation-runs", headers=auth("viewer")).json()
    assert runs["total"] == 2 and [r["id"] for r in runs["items"]] == [second["id"], first["id"]]
    assert client.get(f"/projects/{project['id']}/validation-runs/latest", headers=auth("viewer")).json()["id"] == second["id"]
    assert client.get(f"/validation-runs/{first['id']}", headers=auth("viewer")).json()["created_by_name"] == "Engineer"
    assert client.get("/validation-runs/nope", headers=auth("viewer")).status_code == 404

    assert issues(client, auth, second, "?severity=high")["total"] == 5
    assert issues(client, auth, second, "?status=acknowledged")["total"] == 0
    assert issues(client, auth, second, "?rule_id=STALE_DEPENDENCY")["total"] == 3
    assert issues(client, auth, second, f"?document_id={docs['S-201']['id']}")["total"] == 2
    page = issues(client, auth, second, "?limit=2&offset=6")
    assert page["total"] == 7 and len(page["items"]) == 1
    assert client.get(f"/validation-runs/{second['id']}/issues?severity=extreme", headers=auth("viewer")).status_code == 422
    assert [i["message"] for i in issues(client, auth, first)["items"]] == [i["message"] for i in issues(client, auth, second)["items"]]


def test_validation_is_audited_and_removed_with_the_project(client, auth, project, factory, session_factory):
    from sqlalchemy import func, select

    from app.models.validation import IssueAcknowledgement, ValidationIssue, ValidationRun
    run = validate(client, auth, project)
    issue = issues(client, auth, run, "?severity=medium")["items"][0]
    client.post(f"/issues/{issue['id']}/acknowledge", headers=auth("reviewer"), json={"note": "Accepted for this issue"})
    actions = {i["action"] for i in client.get(f"/audit-logs?project_id={project['id']}&limit=200", headers=auth("admin")).json()["items"]}
    assert {"validation.run", "issue.acknowledged"} <= actions
    assert client.delete(f"/projects/{project['id']}", headers=auth("admin")).status_code == 204
    with session_factory() as db:
        for model_ in (ValidationRun, ValidationIssue, IssueAcknowledgement):
            assert db.scalar(select(func.count()).select_from(model_)) == 0
