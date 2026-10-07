from pathlib import Path

from app.core.config import get_settings
from tests.conftest import upload


def test_create_requires_manage_role(client, auth):
    body = {"name": "P"}
    assert client.post("/projects", json=body, headers=auth("engineer")).status_code == 403
    assert client.post("/projects", json=body, headers=auth("viewer")).status_code == 403
    assert client.post("/projects", json=body, headers=auth("bim_coordinator")).status_code == 201


def test_create_validates_name(client, auth):
    r = client.post("/projects", json={"name": "   "}, headers=auth("admin"))
    assert r.status_code == 422


def test_list_get_and_search(client, auth, project):
    h = auth("viewer")
    page = client.get("/projects", headers=h).json()
    assert page["total"] == 1 and page["items"][0]["document_count"] == 0
    assert client.get("/projects?q=factory", headers=h).json()["total"] == 1
    assert client.get("/projects?q=nothing-here", headers=h).json()["total"] == 0
    assert client.get(f"/projects/{project['id']}", headers=h).json()["name"] == project["name"]
    assert client.get("/projects/does-not-exist", headers=h).status_code == 404


def test_rename_and_audit(client, auth, project):
    r = client.patch(f"/projects/{project['id']}", json={"name": "Factory Expansion - Building B"},
                     headers=auth("bim_coordinator"))
    assert r.status_code == 200 and r.json()["name"].endswith("Building B")
    logs = client.get(f"/audit-logs?project_id={project['id']}", headers=auth("admin")).json()["items"]
    assert "project.updated" in [i["action"] for i in logs]


def test_archive_blocks_new_documents(client, auth, project):
    h = auth("bim_coordinator")
    assert client.patch(f"/projects/{project['id']}", json={"status": "archived"}, headers=h).status_code == 200
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "S-201", "name": "Framing", "discipline": "structure"})
    assert r.status_code == 409 and "archived" in r.json()["detail"]
    assert client.get("/projects?status=active", headers=h).json()["total"] == 0
    client.patch(f"/projects/{project['id']}", json={"status": "active"}, headers=h)
    assert client.get("/projects?status=active", headers=h).json()["total"] == 1


def test_delete_is_admin_only_and_removes_files(client, auth, project, document):
    assert upload(client, auth("engineer"), document["id"]).status_code == 201
    storage_dir = Path(get_settings().storage_dir) / project["id"]
    assert storage_dir.exists()
    assert client.delete(f"/projects/{project['id']}", headers=auth("bim_coordinator")).status_code == 403
    assert client.delete(f"/projects/{project['id']}", headers=auth("admin")).status_code == 204
    assert client.get(f"/projects/{project['id']}", headers=auth("admin")).status_code == 404
    assert not storage_dir.exists()
    assert client.get(f"/documents/{document['id']}", headers=auth("admin")).status_code == 404
