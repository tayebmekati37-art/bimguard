from app.models.bim import BimElement
from app.models.document import DocumentRevision


def _make_doc_and_revision(client, auth, project, session_factory, *,
                            extraction_status="ok", file_path="stored/does-not-exist.ifc",
                            original_filename="architecture.ifc", element_count=0):
    doc = client.post(
        f"/projects/{project['id']}/documents",
        headers=auth("engineer"),
        json={"document_number": "A-101", "name": "Arch", "discipline": "architecture"},
    ).json()
    with session_factory() as db:
        rev = DocumentRevision(
            document_id=doc["id"], revision_number=1, file_path=file_path,
            original_filename=original_filename, file_size=100, checksum="chk",
            created_by_name="tester", status="approved",
            extraction_status=extraction_status, element_count=element_count,
        )
        db.add(rev)
        db.commit()
        revision_id = rev.id
    return doc["id"], revision_id


def _add_elements(session_factory, revision_id, *rows):
    with session_factory() as db:
        for guid, cls, tag, level, room, material in rows:
            db.add(BimElement(
                revision_id=revision_id, guid=guid, ifc_class=cls, tag=tag,
                level=level, room=room, material=material,
                fingerprint=f"fp-{guid}", properties={"Pset.Wall.IsExternal": True},
                geometry={"location": [1.0, 2.0, 3.0]},
            ))
        db.commit()


# ------------------------------------------------------------------ export

def test_export_requires_auth(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(client, auth, project, session_factory)
    r = client.get(f"/revisions/{rev_id}/elements.json")
    assert r.status_code == 401


def test_export_unknown_revision_404(client, auth):
    r = client.get("/revisions/does-not-exist/elements.json", headers=auth("engineer"))
    assert r.status_code == 404


def test_export_empty_revision(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(client, auth, project, session_factory)
    r = client.get(f"/revisions/{rev_id}/elements.json", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema"] == "bimguard.elements/1"
    assert body["elements"] == []
    assert r.headers.get("content-disposition", "").startswith("attachment")


def test_export_contains_element_data(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(client, auth, project, session_factory)
    _add_elements(session_factory, rev_id, ("g1", "IfcWall", "W-204", "L2", "201", "concrete"))
    r = client.get(f"/revisions/{rev_id}/elements.json", headers=auth("engineer"))
    body = r.json()
    assert len(body["elements"]) == 1
    el = body["elements"][0]
    assert el["id"] == "g1"
    assert el["class"] == "IfcWall"
    assert el["tag"] == "W-204"
    assert el["level"] == "L2"
    assert el["room"] == "201"
    assert el["material"] == "concrete"


# ------------------------------------------------------------------ round-trip

def test_verify_round_trip_unknown_revision_404(client, auth):
    r = client.post("/revisions/nope/verify-round-trip", headers=auth("engineer"))
    assert r.status_code == 404


def test_verify_round_trip_empty_ok(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(client, auth, project, session_factory)
    r = client.post(f"/revisions/{rev_id}/verify-round-trip", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["element_count"] == 0


def test_verify_round_trip_with_elements_ok(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(client, auth, project, session_factory)
    _add_elements(
        session_factory, rev_id,
        ("g1", "IfcWall", "W-204", "L2", "201", "concrete"),
        ("g2", "IfcSlab", "S-101", "L2", None, None),
        ("g3", "IfcDoor", "D-001", "L1", "101", "timber"),
    )
    r = client.post(f"/revisions/{rev_id}/verify-round-trip", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["element_count"] == 3
    assert body["matches"] == 3
    assert body["missing"] == []
    assert body["extra"] == []
    assert body["mismatches"] == []


# ------------------------------------------------------------------ source verification

def test_verify_source_unknown_revision_404(client, auth):
    r = client.post("/revisions/nope/verify-source", headers=auth("engineer"))
    assert r.status_code == 404


def test_verify_source_skips_when_not_extracted(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(
        client, auth, project, session_factory, extraction_status="pending"
    )
    r = client.post(f"/revisions/{rev_id}/verify-source", headers=auth("engineer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert "not 'ok'" in body["reason"]
    assert body["source_format"] == "ifc"


def test_verify_source_skips_when_file_missing(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(
        client, auth, project, session_factory,
        extraction_status="ok", file_path="stored/missing.ifc",
    )
    r = client.post(f"/revisions/{rev_id}/verify-source", headers=auth("engineer"))
    body = r.json()
    assert body["ok"] is False
    assert "missing" in body["reason"].lower() or "path" in body["reason"].lower()


def test_verify_source_unsupported_format(client, auth, project, session_factory):
    _, rev_id = _make_doc_and_revision(
        client, auth, project, session_factory,
        extraction_status="ok", original_filename="drawing.dwg",
    )
    r = client.post(f"/revisions/{rev_id}/verify-source", headers=auth("engineer"))
    body = r.json()
    assert body["ok"] is False
    assert "dwg" in body["source_format"]
    assert "cannot be re-parsed" in body["reason"].lower()