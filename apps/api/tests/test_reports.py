import json


def _make_doc(client, auth, project_id, number, name, discipline):
    r = client.post(
        f"/projects/{project_id}/documents",
        headers=auth("engineer"),
        json={"document_number": number, "name": name, "discipline": discipline},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_json_report_requires_auth(client, project):
    r = client.get(f"/projects/{project['id']}/reports/readiness.json")
    assert r.status_code == 401


def test_json_report_unknown_project(client, auth):
    r = client.get("/projects/does-not-exist/reports/readiness.json", headers=auth("engineer"))
    assert r.status_code == 404


def test_json_report_empty_project(client, auth, project):
    r = client.get(f"/projects/{project['id']}/reports/readiness.json", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    body = json.loads(r.content)
    assert body["schema_version"] == 1
    assert body["project"]["id"] == project["id"]
    assert body["project"]["name"] == project["name"]
    assert body["summary"]["readiness_status"] == "NOT_VALIDATED"
    assert body["summary"]["documents"] == 0
    assert body["issues"] == []
    assert body["validation"] is None


def test_json_report_with_validation(client, auth, project):
    _make_doc(client, auth, project["id"], "A-101", "Floor Plan", "architecture")
    rv = client.post(f"/projects/{project['id']}/validate", headers=auth("bim_coordinator"))
    assert rv.status_code == 201, rv.text

    r = client.get(f"/projects/{project['id']}/reports/readiness.json", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = json.loads(r.content)
    assert body["validation"] is not None
    assert body["validation"]["id"] == rv.json()["id"]
    assert body["summary"]["readiness_status"] in ("BLOCKED", "READY_WITH_WARNINGS", "READY")


def test_csv_report_content_type_and_rows(client, auth, project):
    _make_doc(client, auth, project["id"], "A-101", "Floor Plan", "architecture")
    r = client.get(f"/projects/{project['id']}/reports/readiness.csv", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    assert "BIMGuard Readiness Report" in text
    assert project["name"] in text
    assert "Severity,Document,Element,Rule ID,Title,Status" in text
    assert r.headers.get("content-disposition", "").startswith("attachment")


def test_csv_empty_project(client, auth, project):
    r = client.get(f"/projects/{project['id']}/reports/readiness.csv", headers=auth("engineer"))
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert "NOT_VALIDATED" in text


def test_pdf_report_starts_with_magic_bytes(client, auth, project):
    r = client.get(f"/projects/{project['id']}/reports/readiness.pdf", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert r.headers.get("content-disposition", "").startswith("attachment")


def test_pdf_report_with_issues(client, auth, project):
    _make_doc(client, auth, project["id"], "A-101", "Floor Plan", "architecture")
    client.post(f"/projects/{project['id']}/validate", headers=auth("bim_coordinator"))
    r = client.get(f"/projects/{project['id']}/reports/readiness.pdf", headers=auth("engineer"))
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 1000


def test_all_three_formats_agree_on_readiness(client, auth, project):
    _make_doc(client, auth, project["id"], "A-101", "Floor Plan", "architecture")
    client.post(f"/projects/{project['id']}/validate", headers=auth("bim_coordinator"))

    j = client.get(f"/projects/{project['id']}/reports/readiness.json", headers=auth("engineer"))
    c = client.get(f"/projects/{project['id']}/reports/readiness.csv", headers=auth("engineer"))
    p = client.get(f"/projects/{project['id']}/reports/readiness.pdf", headers=auth("engineer"))

    status = json.loads(j.content)["summary"]["readiness_status"]
    csv_text = c.content.decode("utf-8-sig")
    assert status in csv_text
    assert p.content[:5] == b"%PDF-"