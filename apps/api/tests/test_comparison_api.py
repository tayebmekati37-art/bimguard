import json
from pathlib import Path

import pytest

from tests.conftest import upload

REPO = Path(__file__).resolve().parents[3]
IFC_DIR = REPO / "data" / "sample_ifc"


def model(*elements):
    return json.dumps({"schema": "bimguard.elements/1", "elements": list(elements)}).encode()


def el(guid, cls, tag, x=None, room=None, props=None):
    geometry = {"location": [x, 0.0, 4500.0], "rotation_deg": 0.0} if x is not None else {}
    return {"id": guid, "class": cls, "tag": tag, "name": f"{cls} {tag}", "level": "L02", "room": room,
            "properties": props or {}, "geometry": geometry}


V1 = model(
    el("w1", "IfcWall", "W-204", 10000.0, props={"Pset_WallCommon.FireRating": "1HR"}),
    el("d1", "IfcDoor", "D-202A", 22000.0, room="205"),
    el("w9", "IfcWall", "W-9", 5000.0),
)
V2 = model(
    el("w1", "IfcWall", "W-204", 10300.0, props={"Pset_WallCommon.FireRating": "2HR"}),
    el("d1", "IfcDoor", "D-202A", 22000.0, room="204"),
    el("w2", "IfcWall", "W-207", 25000.0),
)


def two_revisions(client, auth, document, first=V1, second=V2):
    h = auth("engineer")
    assert upload(client, h, document["id"], content=first, filename="m1.json").status_code == 201
    assert upload(client, h, document["id"], content=second, filename="m2.json").status_code == 201
    revs = client.get(f"/documents/{document['id']}/revisions", headers=h).json()
    return h, revs[1], revs[0]  # headers, old, new


def test_comparison_runs_automatically_after_upload(client, auth, document):
    h, old, new = two_revisions(client, auth, document)
    comp = client.get(f"/revisions/{new['id']}/comparison", headers=h).json()
    assert comp["from_revision_number"] == 1 and comp["to_revision_number"] == 2
    assert comp["document_number"] == "A-101"
    # w1 moved + fire rating, d1 room change, w9 removed, w2 added
    assert comp["total_changes"] == 5
    assert comp["counts"]["by_type"] == {"GEOMETRY_CHANGED": 1, "PARAMETER_CHANGED": 1, "SPATIAL_CHANGED": 1,
                                         "ELEMENT_REMOVED": 1, "ELEMENT_ADDED": 1}
    assert comp["counts"]["by_severity"] == {"MEDIUM": 4, "HIGH": 1}
    assert comp["counts"]["elements_unchanged"] == 0 and comp["config"]["position_tolerance_mm"] == 1.0


def test_first_revision_has_no_comparison(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=V1, filename="m1.json")
    rev = client.get(f"/documents/{document['id']}/revisions", headers=h).json()[0]
    r = client.get(f"/revisions/{rev['id']}/comparison", headers=h)
    assert r.status_code == 404 and "No comparison" in r.json()["detail"]
    r = client.post(f"/revisions/{rev['id']}/compare", headers=h)
    assert r.status_code == 409 and "no earlier revision" in r.json()["detail"]


def test_changes_are_structured_sorted_and_filterable(client, auth, document):
    h, _old, new = two_revisions(client, auth, document)
    cid = client.get(f"/revisions/{new['id']}/comparison", headers=h).json()["id"]
    page = client.get(f"/comparisons/{cid}/changes", headers=h).json()
    assert page["total"] == 5 and page["items"][0]["severity"] == "HIGH"
    move = client.get(f"/comparisons/{cid}/changes?change_type=geometry_changed", headers=h).json()["items"][0]
    assert move["element_tag"] == "W-204" and move["field"] == "location"
    assert move["old_value"] == [10000.0, 0.0, 4500.0] and move["new_value"] == [10300.0, 0.0, 4500.0]
    assert move["severity"] == "MEDIUM" and 0.9 <= move["confidence"] <= 1.0
    assert move["summary"] == "Wall W-204 moved 300 mm (X +300)" or "moved 300 mm" in move["summary"]
    assert move["detail"]["distance_mm"] == 300.0
    assert client.get(f"/comparisons/{cid}/changes?severity=high", headers=h).json()["total"] == 1
    assert client.get(f"/comparisons/{cid}/changes?q=D-202A", headers=h).json()["total"] == 1
    assert client.get(f"/comparisons/{cid}/changes?limit=2&offset=4", headers=h).json()["items"].__len__() == 1


def test_identical_models_produce_no_changes(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=V1, filename="a.json")
    tweaked = json.dumps(json.loads(V1), indent=2).encode()  # different bytes, same elements
    upload(client, h, document["id"], content=tweaked, filename="b.json")
    new = client.get(f"/documents/{document['id']}/revisions", headers=h).json()[0]
    comp = client.get(f"/revisions/{new['id']}/comparison", headers=h).json()
    assert comp["total_changes"] == 0 and comp["counts"]["elements_unchanged"] == 3


def test_rerun_replaces_previous_comparison(client, auth, document):
    h, _old, new = two_revisions(client, auth, document)
    first = client.get(f"/revisions/{new['id']}/comparison", headers=h).json()
    r = client.post(f"/revisions/{new['id']}/compare", headers=h)
    assert r.status_code == 201 and r.json()["total_changes"] == 5 and r.json()["id"] != first["id"]
    assert client.get(f"/comparisons/{first['id']}", headers=h).status_code == 404
    assert client.get(f"/revisions/{new['id']}/comparison", headers=h).json()["id"] == r.json()["id"]


def test_unsupported_model_gives_a_clear_error(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=b"%PDF-1.4 old", filename="spec.pdf")
    upload(client, h, document["id"], content=V1, filename="m1.json")
    new = client.get(f"/documents/{document['id']}/revisions", headers=h).json()[0]
    r = client.post(f"/revisions/{new['id']}/compare", headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == ("Unable to compare revision A-101 v1 with v2 because revision v1 "
                                  "contains no supported model data.")
    assert client.get(f"/revisions/{new['id']}/comparison", headers=h).status_code == 404  # auto-run skipped


def test_failed_extraction_explains_why(client, auth, document):
    h = auth("engineer")
    upload(client, h, document["id"], content=b'{"elements": [{"class": "X"}]}', filename="bad.json")
    upload(client, h, document["id"], content=V1, filename="m1.json")
    new = client.get(f"/documents/{document['id']}/revisions", headers=h).json()[0]
    detail = client.post(f"/revisions/{new['id']}/compare", headers=h).json()["detail"]
    assert "could not be read" in detail and "missing 'id'" in detail


def test_compare_validates_pair_and_permissions(client, auth, document):
    h, old, new = two_revisions(client, auth, document)
    assert client.post(f"/revisions/{new['id']}/compare", headers=auth("viewer")).status_code == 403
    assert client.post(f"/revisions/{new['id']}/compare", headers=auth("reviewer")).status_code == 201
    r = client.post(f"/revisions/{old['id']}/compare", headers=h, json={"against_revision_id": new["id"]})
    assert r.status_code == 409 and "not older" in r.json()["detail"]
    assert client.get(f"/revisions/{new['id']}/comparison", headers=auth("viewer")).status_code == 200


def test_comparison_is_audited(client, auth, project, document):
    two_revisions(client, auth, document)
    items = client.get(f"/audit-logs?project_id={project['id']}&action=revision.compared",
                       headers=auth("admin")).json()["items"]
    assert len(items) == 1 and items[0]["detail"]["changes"] == 5


def test_plan_data_marks_added_removed_and_modified(client, auth, document):
    h, _old, new = two_revisions(client, auth, document)
    cid = client.get(f"/revisions/{new['id']}/comparison", headers=h).json()["id"]
    plan = client.get(f"/comparisons/{cid}/footprints", headers=h).json()
    by_tag = {e["tag"]: e for e in plan["changed"]}
    assert by_tag["W-207"]["status"] == "added" and by_tag["W-207"]["old"] is None
    assert by_tag["W-9"]["status"] == "removed" and by_tag["W-9"]["new"] is None
    wall = by_tag["W-204"]
    assert wall["status"] == "modified" and wall["old"]["location"][0] == 10000.0 and wall["new"]["location"][0] == 10300.0
    assert plan["context"] == []


def test_deleting_a_project_removes_comparisons(client, auth, project, document, session_factory):
    from sqlalchemy import func, select
    from app.models.comparison import DetectedChange, RevisionComparison
    two_revisions(client, auth, document)
    assert client.delete(f"/projects/{project['id']}", headers=auth("admin")).status_code == 204
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RevisionComparison)) == 0
        assert db.scalar(select(func.count()).select_from(DetectedChange)) == 0


# ---- the real demo scenario, end to end through IfcOpenShell ----
def test_architecture_v1_to_v2_detects_the_demo_changes(client, auth, document):
    pytest.importorskip("ifcopenshell")
    h = auth("engineer")
    for version in ("v1", "v2"):
        content = (IFC_DIR / f"architecture_{version}.ifc").read_bytes()
        assert upload(client, h, document["id"], content=content, filename=f"architecture_{version}.ifc").status_code == 201
    new = client.get(f"/documents/{document['id']}/revisions", headers=h).json()[0]
    comp = client.get(f"/revisions/{new['id']}/comparison", headers=h).json()
    assert comp["counts"]["by_type"] == {"GEOMETRY_CHANGED": 4, "SPATIAL_CHANGED": 1, "PARAMETER_CHANGED": 5,
                                         "ELEMENT_ADDED": 1}
    assert comp["total_changes"] == 11 and comp["counts"]["elements_unchanged"] == 14

    changes = client.get(f"/comparisons/{comp['id']}/changes?limit=100", headers=h).json()["items"]
    by = {(c["element_tag"], c["field"]): c for c in changes}
    wall = by[("W-204", "location")]
    assert wall["detail"]["distance_mm"] == 300.0 and wall["severity"] == "MEDIUM"
    assert by[("D-204A", "location")]["detail"]["delta_mm"] == [300.0, 0.0, 0.0]
    door = by[("D-202A", "location")]
    assert door["detail"]["distance_mm"] == 10000.0 and door["severity"] == "HIGH"
    room = by[("D-202A", "room")]
    assert (room["old_value"], room["new_value"], room["change_type"]) == ("205", "204", "SPATIAL_CHANGED")
    assert by[("204", "Pset_SpaceCommon.OccupancyType")]["new_value"] == "Switchgear Room"
    assert by[("204", "Qto_SpaceBaseQuantities.NetFloorArea")]["new_value"] == 77.6
    assert by[("203", "Qto_SpaceBaseQuantities.NetFloorArea")]["new_value"] == 82.4
    assert by[("W-207", "element")]["change_type"] == "ELEMENT_ADDED"
    assert all(0.8 <= c["confidence"] <= 1.0 for c in changes)

    plan = client.get(f"/comparisons/{comp['id']}/footprints", headers=h).json()
    walls = {e["tag"]: e for e in plan["changed"]}
    assert walls["W-204"]["old"]["footprint"] == {"x0": 0.0, "y0": -100.0, "x1": 8000.0, "y1": 100.0, "height": 4000.0}
    assert len(plan["context"]) == 14 and plan["changed"][0]["status"] in ("modified", "added")
