import json
from pathlib import Path

import pytest

from tests.conftest import upload

REPO = Path(__file__).resolve().parents[3]
IFC_DIR = REPO / "data" / "sample_ifc"
JSON_DIR = REPO / "data" / "sample_projects" / "factory_expansion"


def revision(client, headers, doc_id):
    return client.get(f"/documents/{doc_id}/revisions", headers=headers).json()[0]


def test_json_upload_is_extracted(client, auth, document):
    h = auth("engineer")
    content = (JSON_DIR / "equipment_v1.json").read_bytes()
    assert upload(client, h, document["id"], content=content, filename="equipment_v1.json").status_code == 201
    rev = revision(client, h, document["id"])
    assert rev["extraction_status"] == "ok" and rev["element_count"] == 3
    assert rev["model_schema"] == "bimguard.elements/1"

    page = client.get(f"/revisions/{rev['id']}/elements", headers=h).json()
    assert page["total"] == 3
    assert client.get(f"/revisions/{rev['id']}/elements?room=204", headers=h).json()["items"][0]["tag"] == "SWG-040"
    assert client.get(f"/revisions/{rev['id']}/elements?q=compressor", headers=h).json()["total"] == 1
    assert client.get(f"/revisions/{rev['id']}/elements?limit=2", headers=h).json()["total"] == 3
    one = client.get(f"/revisions/{rev['id']}/elements/CMP-020", headers=h).json()
    assert one["properties"]["PowerKW"] == 55.0 and one["geometry"]["location"][0] == 27000
    assert client.get(f"/revisions/{rev['id']}/elements/nope", headers=h).status_code == 404


def test_summary_counts(client, auth, document):
    h = auth("engineer")
    content = (JSON_DIR / "quantity_v1.json").read_bytes()
    upload(client, h, document["id"], content=content, filename="quantity_v1.json")
    rev = revision(client, h, document["id"])
    summary = client.get(f"/revisions/{rev['id']}/summary", headers=auth("viewer")).json()
    assert summary["total"] == 6
    assert summary["by_class"] == [{"key": "QuantityItem", "count": 6}]
    assert summary["by_level"] == [{"key": "L02", "count": 6}]


def test_invalid_model_reports_clear_failure(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=json.dumps({"elements": [{"class": "X"}]}).encode(),
           filename="broken.json")
    rev = revision(client, h, document["id"])
    assert rev["extraction_status"] == "failed" and "missing 'id'" in rev["extraction_message"]
    assert client.get(f"/revisions/{rev['id']}/elements", headers=h).json()["total"] == 0


def test_non_model_file_is_marked_unsupported(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=b"%PDF-1.4 test", filename="spec.pdf")
    assert revision(client, h, document["id"])["extraction_status"] == "unsupported"


def test_reextract_requires_edit_role_and_rebuilds(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=(JSON_DIR / "equipment_v1.json").read_bytes(), filename="e.json")
    rev = revision(client, h, document["id"])
    assert client.post(f"/revisions/{rev['id']}/extract", headers=auth("viewer")).status_code == 403
    r = client.post(f"/revisions/{rev['id']}/extract", headers=h)
    assert r.status_code == 202
    again = revision(client, h, document["id"])
    assert again["extraction_status"] == "ok" and again["element_count"] == 3
    assert client.get(f"/revisions/{rev['id']}/elements", headers=h).json()["total"] == 3


def test_extraction_is_audited(client, auth, project, document):
    upload(client, auth("engineer"), document["id"], content=(JSON_DIR / "equipment_v1.json").read_bytes(),
           filename="e.json")
    items = client.get(f"/audit-logs?project_id={project['id']}", headers=auth("admin")).json()["items"]
    assert "revision.extracted" in {i["action"] for i in items}


def test_ifc_upload_is_extracted(client, auth, document):
    pytest.importorskip("ifcopenshell")
    h = auth("engineer")
    for version, expected in (("v1", 19), ("v2", 20)):
        content = (IFC_DIR / f"architecture_{version}.ifc").read_bytes()
        assert upload(client, h, document["id"], content=content,
                      filename=f"architecture_{version}.ifc").status_code == 201
        rev = revision(client, h, document["id"])
        assert rev["extraction_status"] == "ok" and rev["element_count"] == expected
        assert rev["model_schema"] == "IFC4"
    wall = client.get(f"/revisions/{rev['id']}/elements?q=W-204", headers=h).json()["items"][0]
    assert wall["geometry"]["location"][0] == 10300.0


def test_interrupted_extractions_are_requeued(client, auth, document, session_factory):
    from sqlalchemy import update

    from app.models.document import DocumentRevision
    from app.services.extraction import requeue_pending

    h = auth("engineer")
    upload(client, h, document["id"], content=(JSON_DIR / "equipment_v1.json").read_bytes(), filename="e.json")
    with session_factory() as db:  # simulate a server restart that left the revision pending
        db.execute(update(DocumentRevision).values(extraction_status="pending", element_count=None))
        db.commit()
    assert revision(client, h, document["id"])["extraction_status"] == "pending"
    assert requeue_pending(session_factory) == 1
    again = revision(client, h, document["id"])
    assert again["extraction_status"] == "ok" and again["element_count"] == 3
    assert requeue_pending(session_factory) == 0


def test_out_of_order_extraction_still_produces_the_comparison(client, auth, document, session_factory):
    from sqlalchemy import update

    from app.models.document import DocumentRevision
    from app.services.extraction import requeue_pending

    h = auth("engineer")
    v1 = json.dumps({"elements": [{"id": "a", "class": "IfcWall", "tag": "W-1",
                                   "geometry": {"location": [0.0, 0.0, 0.0]}}]}).encode()
    v2 = json.dumps({"elements": [{"id": "a", "class": "IfcWall", "tag": "W-1",
                                   "geometry": {"location": [300.0, 0.0, 0.0]}}]}).encode()
    upload(client, h, document["id"], content=v1, filename="a.json")
    upload(client, h, document["id"], content=v2, filename="b.json")
    newest = client.get(f"/documents/{document['id']}/revisions", headers=h).json()[0]
    assert client.get(f"/revisions/{newest['id']}/comparison", headers=h).json()["total_changes"] == 1
    # the older revision's extraction "finishes later": the pair must be compared again, not lost
    with session_factory() as db:
        db.execute(update(DocumentRevision).where(DocumentRevision.revision_number == 1)
                   .values(extraction_status="pending"))
        db.commit()
    assert requeue_pending(session_factory) == 1
    assert client.get(f"/revisions/{newest['id']}/comparison", headers=h).json()["total_changes"] == 1
