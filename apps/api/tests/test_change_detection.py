import random

import pytest

from app.bim.types import ElementData
from app.engines.change_detection import (
    ChangeType as T, RevisionMeta, Severity as S, detect_changes, detect_revision_metadata_changes,
)


def wall(guid="w1", tag="W-204", x=10000.0, y=0.0, rot=90.0, length=8000.0, **kw):
    base = dict(
        guid=guid, ifc_class="IfcWall", name=f"Wall {tag}", tag=tag, level="L02", room=None,
        material="CMU", properties={"Pset_WallCommon.FireRating": "1HR", "Pset_WallCommon.LoadBearing": False},
        geometry={"location": [x, y, 4500.0], "rotation_deg": rot, "dimensions": {"Length": length, "Width": 200.0}})
    base.update(kw)
    return ElementData(**base)


def one(changes, change_type=None, field=None):
    found = [c for c in changes if (change_type is None or c.change_type == change_type)
             and (field is None or c.field == field)]
    assert len(found) == 1, found
    return found[0]


def test_no_changes_means_no_records():
    assert detect_changes([wall()], [wall()]) == []


def test_wall_moved_300mm():
    changes = detect_changes([wall()], [wall(x=10300.0)])
    c = one(changes)
    assert c.change_type == T.GEOMETRY_CHANGED and c.field == "location"
    assert c.old_value == [10000.0, 0.0, 4500.0] and c.new_value == [10300.0, 0.0, 4500.0]
    assert c.severity == S.MEDIUM and 0.9 <= c.confidence <= 1.0
    assert c.detail["distance_mm"] == 300.0 and c.detail["delta_mm"] == [300.0, 0.0, 0.0]
    assert c.summary == "Wall W-204 moved 300 mm (X +300)"
    assert c.element_guid == "w1" and c.match_method == "guid"


def test_movement_below_tolerance_is_ignored():
    assert detect_changes([wall()], [wall(x=10000.5)]) == []


@pytest.mark.parametrize("dx,expected", [(50.0, S.LOW), (100.0, S.MEDIUM), (499.0, S.MEDIUM), (500.0, S.HIGH)])
def test_movement_severity_bands(dx, expected):
    assert one(detect_changes([wall()], [wall(x=10000 + dx)])).severity == expected


def test_structural_elements_are_one_level_more_severe():
    col = lambda x: ElementData(guid="c1", ifc_class="IfcColumn", tag="C-B1", geometry={"location": [x, 0.0, 0.0]})  # noqa: E731
    assert one(detect_changes([col(10000.0)], [col(10300.0)])).severity == S.HIGH
    load_bearing = lambda x: wall(x=x, properties={"Pset_WallCommon.LoadBearing": True})  # noqa: E731
    assert one(detect_changes([load_bearing(10000.0)], [load_bearing(10300.0)])).severity == S.HIGH


def test_rotation_uses_shortest_angle():
    assert detect_changes([wall(rot=359.95)], [wall(rot=0.05)]) == []
    c = one(detect_changes([wall(rot=90.0)], [wall(rot=180.0)]))
    assert c.field == "rotation_deg" and c.severity == S.HIGH and c.detail["delta_deg"] == 90.0


def test_dimension_change():
    c = one(detect_changes([wall()], [wall(length=8500.0)]))
    assert c.field == "dimensions.Length" and c.old_value == 8000.0 and c.new_value == 8500.0
    assert c.severity == S.HIGH and "length changed from 8000 to 8500 mm" in c.summary


def test_room_change_is_spatial_and_movement_is_geometry():
    old = ElementData(guid="d1", ifc_class="IfcDoor", tag="D-202A", room="205", level="L02",
                      geometry={"location": [22000.0, 8000.0, 4500.0]})
    new = ElementData(guid="d1", ifc_class="IfcDoor", tag="D-202A", room="204", level="L02",
                      geometry={"location": [12000.0, 8000.0, 4500.0]})
    changes = detect_changes([old], [new])
    assert {c.change_type for c in changes} == {T.GEOMETRY_CHANGED, T.SPATIAL_CHANGED}
    spatial = one(changes, T.SPATIAL_CHANGED)
    assert spatial.field == "room" and spatial.severity == S.MEDIUM
    assert spatial.summary == "Door D-202A moved from room 205 to room 204"
    assert one(changes, T.GEOMETRY_CHANGED).severity == S.HIGH


def test_level_change_is_high():
    c = one(detect_changes([wall(level="L02")], [wall(level="L03")]))
    assert c.change_type == T.SPATIAL_CHANGED and c.field == "level" and c.severity == S.HIGH


def test_added_and_removed_elements():
    changes = detect_changes([wall("w1", "W-1"), wall("w2", "W-2")], [wall("w1", "W-1"), wall("w3", "W-3")])
    removed, added = one(changes, T.ELEMENT_REMOVED), one(changes, T.ELEMENT_ADDED)
    assert removed.element_guid == "w2" and added.element_guid == "w3"
    assert removed.severity == added.severity == S.MEDIUM
    assert removed.confidence == 0.8  # a wall was both added and removed: could be a rename
    assert added.summary == "Wall W-3 added on level L02"


def test_unambiguous_addition_has_higher_confidence_and_room_in_summary():
    room = ElementData(guid="s9", ifc_class="IfcSpace", tag="206", name="206 Store", level="L02", room="206")
    c = one(detect_changes([], [room]))
    assert c.severity == S.HIGH and c.confidence == 0.97 and c.summary == "Space 206 added in room 206"
    door = ElementData(guid="d9", ifc_class="IfcDoor", tag="D-9", room="204")
    assert one(detect_changes([], [door])).summary == "Door D-9 added in room 204"


def test_parameter_changes_and_severity():
    old = wall(properties={"Pset_WallCommon.FireRating": "1HR", "Pset_WallCommon.Reference": "A", "Gone.Prop": 1})
    new = wall(properties={"Pset_WallCommon.FireRating": "2HR", "Pset_WallCommon.Reference": "A", "New.Prop": 2})
    changes = detect_changes([old], [new])
    assert {c.field for c in changes} == {"Pset_WallCommon.FireRating", "Gone.Prop", "New.Prop"}
    fire = one(changes, field="Pset_WallCommon.FireRating")
    assert fire.change_type == T.PARAMETER_CHANGED and fire.severity == S.HIGH
    assert fire.summary == "Wall W-204: Pset_WallCommon.FireRating changed from 1HR to 2HR"
    assert one(changes, field="Gone.Prop").new_value is None and one(changes, field="Gone.Prop").severity == S.LOW
    assert "removed (was 1)" in one(changes, field="Gone.Prop").summary


def test_quantity_and_significant_parameter_severity():
    def space(area, occupancy):
        return ElementData(guid="s1", ifc_class="IfcSpace", tag="204", properties={
            "Qto_SpaceBaseQuantities.NetFloorArea": area, "Pset_SpaceCommon.OccupancyType": occupancy})
    changes = detect_changes([space(80.0, "Electrical Room")], [space(77.6, "Switchgear Room")])
    assert one(changes, field="Qto_SpaceBaseQuantities.NetFloorArea").severity == S.MEDIUM  # 3% change
    assert one(changes, field="Pset_SpaceCommon.OccupancyType").severity == S.MEDIUM
    tiny = detect_changes([space(80.0, "x")], [space(80.2, "x")])
    assert one(tiny).severity == S.LOW  # 0.25% change
    assert detect_changes([space(80.0, "x")], [space(80.0004, "x")]) == []  # below numeric tolerance


def test_material_change_is_high():
    c = one(detect_changes([wall(material="Concrete")], [wall(material="Steel")]))
    assert c.change_type == T.PARAMETER_CHANGED and c.field == "material" and c.severity == S.HIGH
    assert c.old_value == "Concrete" and c.new_value == "Steel"


def test_classification_change():
    changes = detect_changes([wall()], [wall(ifc_class="IfcBeam")])
    c = one(changes, T.CLASSIFICATION_CHANGED)
    assert c.old_value == "IfcWall" and c.new_value == "IfcBeam" and c.severity == S.HIGH


def test_name_change_is_low_metadata():
    c = one(detect_changes([wall(name="Old")], [wall(name="New")]))
    assert c.change_type == T.METADATA_CHANGED and c.field == "name" and c.severity == S.LOW


def test_regenerated_ids_are_matched_by_class_and_tag():
    changes = detect_changes([wall("old-id")], [wall("new-id", x=10300.0)])
    assert not [c for c in changes if c.change_type in (T.ELEMENT_ADDED, T.ELEMENT_REMOVED)]
    geometry = one(changes, T.GEOMETRY_CHANGED)
    assert geometry.match_method == "tag" and geometry.confidence <= 0.85
    assert geometry.detail["old_guid"] == "old-id" and geometry.element_guid == "new-id"
    assert one(changes, T.METADATA_CHANGED, "guid").old_value == "old-id"


def test_duplicate_tags_are_not_force_matched():
    changes = detect_changes([wall("a"), wall("b")], [wall("c"), wall("d")])
    assert sorted(c.change_type for c in changes) == [T.ELEMENT_ADDED] * 2 + [T.ELEMENT_REMOVED] * 2


def test_revision_metadata_changes():
    changes = detect_revision_metadata_changes(RevisionMeta("draft", "IFC2X3"), RevisionMeta("issued", "IFC4"))
    assert {c.field for c in changes} == {"model_schema", "status"}
    status = one(changes, field="status")
    assert status.severity == S.MEDIUM and status.element_guid is None
    assert status.summary == "Revision status changed from draft to issued"
    # superseded is set automatically by the system, so it is not reported
    assert detect_revision_metadata_changes(RevisionMeta("superseded", "IFC4"), RevisionMeta("draft", "IFC4")) == []


def test_output_is_deterministic_regardless_of_input_order():
    old = [wall(f"w{i}", f"W-{i}", x=1000.0 * i) for i in range(30)]
    new = [wall(f"w{i}", f"W-{i}", x=1000.0 * i + (300 if i % 3 == 0 else 0)) for i in range(5, 35)]
    expected = detect_changes(old, new)
    for seed in range(3):
        a, b = old[:], new[:]
        random.Random(seed).shuffle(a)
        random.Random(seed + 10).shuffle(b)
        assert detect_changes(a, b) == expected
    assert len(expected) > 5


def test_footprint_change_reported_only_when_dimensions_did_not_change():
    fp = lambda x1: {"x0": 0.0, "y0": -100.0, "x1": x1, "y1": 100.0, "height": 4000.0}  # noqa: E731
    def el(x1, length):
        return wall(geometry={"location": [0.0, 0.0, 0.0], "dimensions": {"Length": length}, "footprint": fp(x1)})
    only_fp = detect_changes([el(8000.0, 8000.0)], [el(8400.0, 8000.0)])
    assert one(only_fp).field == "footprint"
    both = detect_changes([el(8000.0, 8000.0)], [el(8400.0, 8400.0)])
    assert one(both).field == "dimensions.Length"
