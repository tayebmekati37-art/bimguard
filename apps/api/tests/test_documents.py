import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.document import DocumentRevision, ImmutableRevisionError
from app.services.storage import safe_filename
from tests.conftest import IFC_V1, IFC_V2, upload


def test_create_document_and_duplicate_number(client, auth, project, document):
    assert document["document_number"] == "A-101"
    assert document["current_revision_number"] is None
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "A-101", "name": "Other", "discipline": "architecture"})
    assert r.status_code == 409


def test_viewer_cannot_create_or_upload(client, auth, project, document):
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("viewer"),
                    json={"document_number": "X-1", "name": "n", "discipline": "general"})
    assert r.status_code == 403
    assert upload(client, auth("viewer"), document["id"]).status_code == 403


def test_invalid_document_number_rejected(client, auth, project):
    r = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                    json={"document_number": "../etc", "name": "n", "discipline": "general"})
    assert r.status_code == 422


def test_revision_sequence_and_supersede(client, auth, document):
    h = auth("engineer")
    first = upload(client, h, document["id"], change_summary="Initial")
    assert first.status_code == 201 and first.json()["revision_number"] == 1
    second = upload(client, h, document["id"], content=IFC_V2, filename="architecture_v2.ifc",
                    change_summary="Wall moved")
    assert second.status_code == 201 and second.json()["revision_number"] == 2
    assert second.json()["previous_revision_id"] == first.json()["id"]

    revs = client.get(f"/documents/{document['id']}/revisions", headers=h).json()
    assert [r["revision_number"] for r in revs] == [2, 1]
    assert revs[1]["status"] == "superseded"
    doc = client.get(f"/documents/{document['id']}", headers=h).json()
    assert doc["current_revision_number"] == 2 and doc["file_type"] == "ifc"
    assert doc["checksum"] == second.json()["checksum"]


def test_explicit_revision_number_must_increase(client, auth, document):
    h = auth("engineer")
    assert upload(client, h, document["id"], revision_number="12").json()["revision_number"] == 12
    r = upload(client, h, document["id"], content=IFC_V2, revision_number="12")
    assert r.status_code == 409 and "newer" in r.json()["detail"]
    assert upload(client, h, document["id"], content=IFC_V2, revision_number="13").status_code == 201


def test_duplicate_file_is_detected(client, auth, document):
    h = auth("engineer")
    assert upload(client, h, document["id"]).status_code == 201
    r = upload(client, h, document["id"])
    assert r.status_code == 409 and "identical" in r.json()["detail"]
    assert len(client.get(f"/documents/{document['id']}/revisions", headers=h).json()) == 1


def test_checksum_is_sha256_of_content(client, auth, document):
    import hashlib
    r = upload(client, auth("engineer"), document["id"])
    assert r.json()["checksum"] == hashlib.sha256(IFC_V1).hexdigest()


def test_rejects_unsupported_type_and_bad_signature(client, auth, document):
    h = auth("engineer")
    assert upload(client, h, document["id"], content=b"MZ...", filename="tool.exe").status_code == 422
    assert upload(client, h, document["id"], content=b"not an ifc", filename="x.ifc").status_code == 422
    assert upload(client, h, document["id"], content=b"", filename="x.json").status_code == 422


def test_rejects_oversized_upload(client, auth, document, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = b"ISO-10303-21;" + b"0" * (1024 * 1024 + 10)
    assert upload(client, auth("engineer"), document["id"], content=big).status_code == 413


def test_path_traversal_filename_is_neutralised(client, auth, document):
    r = upload(client, auth("engineer"), document["id"], filename="../../evil.ifc")
    assert r.status_code == 201 and r.json()["original_filename"] == "evil.ifc"
    assert safe_filename("..\\..\\a b$.IFC") == "a_b_.IFC"


def test_download_returns_original_bytes(client, auth, document):
    h = auth("viewer")
    rev = upload(client, auth("engineer"), document["id"]).json()
    r = client.get(f"/revisions/{rev['id']}/download", headers=h)
    assert r.status_code == 200 and r.content == IFC_V1


def test_status_workflow_and_permissions(client, auth, document):
    rev = upload(client, auth("engineer"), document["id"]).json()
    url = f"/revisions/{rev['id']}/status"
    assert client.patch(url, json={"status": "approved"}, headers=auth("engineer")).status_code == 409  # draft -> approved
    assert client.patch(url, json={"status": "in_review"}, headers=auth("engineer")).status_code == 200
    assert client.patch(url, json={"status": "approved"}, headers=auth("engineer")).status_code == 403
    assert client.patch(url, json={"status": "approved"}, headers=auth("viewer")).status_code == 403
    assert client.patch(url, json={"status": "approved"}, headers=auth("reviewer")).status_code == 200
    assert client.patch(url, json={"status": "issued"}, headers=auth("reviewer")).status_code == 200
    doc = client.get(f"/documents/{document['id']}", headers=auth("viewer")).json()
    assert doc["status"] == "issued" and doc["issue_date"] is not None


def test_only_current_revision_changes_status(client, auth, document):
    h = auth("engineer")
    old = upload(client, h, document["id"]).json()
    upload(client, h, document["id"], content=IFC_V2)
    r = client.patch(f"/revisions/{old['id']}/status", json={"status": "in_review"}, headers=h)
    assert r.status_code == 409


def test_revision_history_is_immutable(client, auth, document, session_factory):
    upload(client, auth("engineer"), document["id"])
    with session_factory() as db:
        rev = db.scalars(select(DocumentRevision)).first()
        rev.checksum = "tampered"
        with pytest.raises(ImmutableRevisionError):
            db.commit()


def test_document_filters(client, auth, project, document):
    h = auth("engineer")
    client.post(f"/projects/{project['id']}/documents", headers=h,
                json={"document_number": "S-201", "name": "Framing Plan", "discipline": "structure"})
    base = f"/projects/{project['id']}/documents"
    assert client.get(base, headers=h).json()["total"] == 2
    assert client.get(base + "?discipline=structure", headers=h).json()["total"] == 1
    assert client.get(base + "?q=floor", headers=h).json()["items"][0]["document_number"] == "A-101"
    assert client.get(base + "?status=issued", headers=h).json()["total"] == 0
    assert client.get(base + "?limit=1&offset=1", headers=h).json()["items"][0]["document_number"] == "S-201"


def test_audit_trail_records_key_events(client, auth, project, document):
    upload(client, auth("engineer"), document["id"])
    items = client.get(f"/audit-logs?project_id={project['id']}", headers=auth("admin")).json()["items"]
    actions = {i["action"] for i in items}
    assert {"project.created", "document.created", "revision.created"} <= actions
    assert client.get("/audit-logs", headers=auth("viewer")).status_code == 403
