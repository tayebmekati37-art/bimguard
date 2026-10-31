"""API endpoint tests for IFC export (M34)."""
from app.models.bim import BimElement
from app.models.document import Document, DocumentRevision


def _seed(client, auth, project, session_factory):
    doc = client.post(
        f"/projects/{project['id']}/documents",
        headers=auth("engineer"),
        json={"document_number": "A-101", "name": "X", "discipline": "architecture"},
    ).json()
    with session_factory() as db:
        rev = DocumentRevision(
            document_id=doc["id"], revision_number=1,
            file_path="x", original_filename="a.ifc", file_size=1,
            checksum="c", created_by_name="t", status="approved",
            extraction_status="ok", element_count=1,
        )
        db.add(rev)
        db.flush()
        db.add(BimElement(
            revision_id=rev.id, guid="g1", ifc_class="IfcWall", tag="W-100",
            name="Wall", level="L1", fingerprint="fp1",
            properties={"Pset_WallCommon.IsExternal": True},
        ))
        db.get(Document, doc["id"]).current_revision_number = 1
        db.commit()
        return rev.id


def test_export_ifc_requires_auth(client, auth, project, session_factory):
    rev_id = _seed(client, auth, project, session_factory)
    r = client.get(f"/revisions/{rev_id}/export.ifc")
    assert r.status_code == 401


def test_export_ifc_unknown_revision_404(client, auth):
    r = client.get("/revisions/does-not-exist/export.ifc", headers=auth("engineer"))
    assert r.status_code == 404


def test_export_ifc_content_type(client, auth, project, session_factory):
    rev_id = _seed(client, auth, project, session_factory)
    r = client.get(f"/revisions/{rev_id}/export.ifc", headers=auth("engineer"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("model/ifc")
    assert "attachment" in r.headers.get("content-disposition", "").lower()


def test_export_ifc_body_is_valid_ifc(client, auth, project, session_factory):
    rev_id = _seed(client, auth, project, session_factory)
    r = client.get(f"/revisions/{rev_id}/export.ifc", headers=auth("engineer"))
    assert r.content.startswith(b"ISO-10303-21")
    assert b"END-ISO-10303-21" in r.content[-100:]
    assert b"IFCWALL" in r.content
    assert b"W-100" in r.content