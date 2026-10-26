import io, zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree as ET
from app.models.bim import BimElement
from app.models.document import Document, DocumentRevision
from app.models.validation import ValidationIssue, ValidationRun

def _seed_run(sf, pid, status="BLOCKED"):
    with sf() as db:
        r = ValidationRun(project_id=pid, status=status, created_by_name="Admin",
                          summary={}, rules_snapshot={}, duration_ms=0)
        db.add(r); db.commit(); return r.id

def _seed_issue(sf, rid, pid, **o):
    d = dict(run_id=rid, project_id=pid, rule_id="STALE_DEPENDENCY", severity="HIGH",
             document_id=None, document_number="S-201", element_tag="", title="Stale dep",
             message="msg", recommended_action="act", details={}, fingerprint="fp", status="open")
    d.update(o)
    with sf() as db:
        db.add(ValidationIssue(**d)); db.commit()

def _unzip(c): return zipfile.ZipFile(io.BytesIO(c))

def test_bcf_requires_auth(client):
    assert client.get("/validation-runs/x/bcf").status_code == 401

def test_bcf_404_unknown(client, auth):
    assert client.get("/validation-runs/nope/bcf", headers=auth("engineer")).status_code == 404

def test_bcf_empty_run(client, auth, project, session_factory):
    rid = _seed_run(session_factory, project["id"], "READY")
    r = client.get(f"/validation-runs/{rid}/bcf", headers=auth("engineer"))
    assert r.status_code == 200
    zf = _unzip(r.content); names = zf.namelist()
    assert "bcf.version" in names
    assert [n for n in names if "/" in n] == []
    v = ET.fromstring(zf.read("bcf.version"))
    assert v.get("VersionId") == "2.1"
    assert r.headers["content-type"].startswith("application/vnd.bcf.zip")

def test_bcf_one_open_issue(client, auth, project, session_factory):
    rid = _seed_run(session_factory, project["id"])
    _seed_issue(session_factory, rid, project["id"])
    r = client.get(f"/validation-runs/{rid}/bcf", headers=auth("engineer"))
    zf = _unzip(r.content)
    mf = [n for n in zf.namelist() if n.endswith("markup.bcf")]
    assert len(mf) == 1
    t = ET.fromstring(zf.read(mf[0])).find("Topic")
    assert t.get("TopicStatus") == "Open"
    assert "Stale dep" in (t.findtext("Title") or "")
    labels = [x.text for x in t.findall("Labels/Label")]
    assert "STALE_DEPENDENCY" in labels

def test_bcf_acknowledged_issue(client, auth, project, session_factory):
    rid = _seed_run(session_factory, project["id"])
    _seed_issue(session_factory, rid, project["id"], status="acknowledged",
                acknowledged_by_name="Reviewer", acknowledged_at=datetime.now(UTC),
                acknowledgement_note="accepted")
    r = client.get(f"/validation-runs/{rid}/bcf", headers=auth("engineer"))
    zf = _unzip(r.content)
    mf = next(n for n in zf.namelist() if n.endswith("markup.bcf"))
    t = ET.fromstring(zf.read(mf)).find("Topic")
    assert t.get("TopicStatus") == "Closed"
    c = t.find("Comment")
    assert c is not None and c.findtext("Author") == "Reviewer"

def _mkdoc(client, auth, project, sf, ifc_guid, tag):
    doc = client.post(f"/projects/{project['id']}/documents", headers=auth("engineer"),
                      json={"document_number": "A-101", "name": "X", "discipline": "architecture"}).json()
    with sf() as db:
        rev = DocumentRevision(document_id=doc["id"], revision_number=1,
                               file_path="x", original_filename="a.json", file_size=1,
                               checksum="c", created_by_name="t", status="approved",
                               extraction_status="ok", element_count=1)
        db.add(rev); db.flush()
        db.add(BimElement(revision_id=rev.id, guid=ifc_guid, ifc_class="IfcWall",
                          tag=tag, fingerprint="f1"))
        db.get(Document, doc["id"]).current_revision_number = 1
        db.commit()
    return doc["id"]

def test_bcf_ifc_guid_viewpoint(client, auth, project, session_factory):
    did = _mkdoc(client, auth, project, session_factory, "1aB2c3D4e5F6g7H8i9J0kL", "W-204")
    rid = _seed_run(session_factory, project["id"])
    _seed_issue(session_factory, rid, project["id"], document_id=did,
                element_tag="W-204", document_number="A-101", rule_id="SPATIAL_CONFLICT")
    r = client.get(f"/validation-runs/{rid}/bcf", headers=auth("engineer"))
    zf = _unzip(r.content)
    vp = [n for n in zf.namelist() if n.endswith("viewpoint.bcfv")]
    assert len(vp) == 1
    c = ET.fromstring(zf.read(vp[0])).find("Components/Selection/Component")
    assert c.get("IfcGuid") == "1aB2c3D4e5F6g7H8i9J0kL"

def test_bcf_non_ifc_guid_no_viewpoint(client, auth, project, session_factory):
    did = _mkdoc(client, auth, project, session_factory, "guid-wall-a", "W-204")
    rid = _seed_run(session_factory, project["id"])
    _seed_issue(session_factory, rid, project["id"], document_id=did, element_tag="W-204")
    r = client.get(f"/validation-runs/{rid}/bcf", headers=auth("engineer"))
    zf = _unzip(r.content)
    assert [n for n in zf.namelist() if n.endswith("viewpoint.bcfv")] == []
    assert len([n for n in zf.namelist() if n.endswith("markup.bcf")]) == 1

def test_bcf_all_xml_parses(client, auth, project, session_factory):
    did = _mkdoc(client, auth, project, session_factory, "1aB2c3D4e5F6g7H8i9J0kL", "W-204")
    rid = _seed_run(session_factory, project["id"])
    _seed_issue(session_factory, rid, project["id"], element_tag="W-204", document_id=did)
    _seed_issue(session_factory, rid, project["id"], status="acknowledged",
                acknowledged_by_name="R", acknowledged_at=datetime.now(UTC),
                acknowledgement_note="ok", rule_id="MISSING_METADATA",
                document_number="", element_tag="", severity="MEDIUM")
    r = client.get(f"/validation-runs/{rid}/bcf", headers=auth("engineer"))
    zf = _unzip(r.content)
    n = 0
    for name in zf.namelist():
        if name == "bcf.version" or name.endswith(".bcf") or name.endswith(".bcfv"):
            ET.fromstring(zf.read(name)); n += 1
    assert n >= 3