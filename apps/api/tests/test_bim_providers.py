import json
from pathlib import Path

import pytest

from app.bim.ifc_provider import IfcProvider
from app.bim.json_provider import JsonProvider, MockProvider
from app.bim.provider import BimError
from app.bim.registry import provider_for
from app.bim.types import ElementData

REPO = Path(__file__).resolve().parents[3]
IFC_DIR = REPO / "data" / "sample_ifc"
JSON_DIR = REPO / "data" / "sample_projects" / "factory_expansion"


def by_tag(provider, tag):
    return next(e for e in provider.list_elements() if e.tag == tag)


def test_registry_maps_extensions():
    assert isinstance(provider_for(".IFC"), IfcProvider)
    assert isinstance(provider_for(".json"), JsonProvider)
    assert provider_for(".pdf") is None


def test_fingerprint_is_stable_and_sensitive():
    a = ElementData(guid="1", ifc_class="IfcWall", name="W", properties={"a": 1}, geometry={"location": [0, 0, 0]})
    same = ElementData(guid="other-id", ifc_class="IfcWall", name="W", properties={"a": 1},
                       geometry={"location": [0, 0, 0]})
    moved = ElementData(guid="1", ifc_class="IfcWall", name="W", properties={"a": 1},
                        geometry={"location": [300, 0, 0]})
    assert a.fingerprint() == same.fingerprint()
    assert a.fingerprint() != moved.fingerprint()


def test_mock_provider_contract():
    el = ElementData(guid="w1", ifc_class="IfcWall", properties={"FireRating": "2HR"}, geometry={"location": [1, 2, 3]})
    provider = MockProvider([el])
    assert provider.import_model().element_count == 1
    assert provider.get_properties("w1") == {"FireRating": "2HR"}
    assert provider.get_geometry("w1")["location"] == [1, 2, 3]
    assert provider.get_element("missing") is None
    with pytest.raises(KeyError):
        provider.get_properties("missing")


def test_json_provider_reads_sample_models():
    provider = JsonProvider()
    info = provider.import_model(JSON_DIR / "equipment_v1.json")
    assert info.schema == "bimguard.elements/1" and info.element_count == 3
    swg = provider.get_element("SWG-040")
    assert swg.room == "204" and swg.geometry["location"][0] == 12000


@pytest.mark.parametrize("content,message", [
    ("not json", "could not be read"),
    ('{"foo": 1}', "'elements' list"),
    ('{"elements": [{"class": "X"}]}', "missing 'id'"),
    ('{"elements": [{"id": "a"}]}', "missing 'class'"),
    ('{"elements": [{"id": "a", "class": "X", "properties": []}]}', "must be objects"),
])
def test_json_provider_rejects_bad_models(tmp_path, content, message):
    path = tmp_path / "m.json"
    path.write_text(content)
    with pytest.raises(BimError, match=message):
        JsonProvider().import_model(path)


def test_json_provider_accepts_bom(tmp_path):
    path = tmp_path / "m.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"elements": [{"id": "a", "class": "X"}]}).encode())
    assert JsonProvider().import_model(path).element_count == 1


# ---- real IFC parsing: needs IfcOpenShell; skipped if it is not installed ----
@pytest.fixture()
def ifc_v1():
    pytest.importorskip("ifcopenshell")
    provider = IfcProvider()
    provider.import_model(IFC_DIR / "architecture_v1.ifc")
    return provider


def test_ifc_architecture_extraction(ifc_v1):
    elements = list(ifc_v1.list_elements())
    assert len(elements) == 19
    wall = by_tag(ifc_v1, "W-204")
    assert wall.ifc_class == "IfcWall" and wall.level == "L02" and wall.material == "Concrete masonry unit"
    assert wall.geometry["location"] == [10000.0, 0.0, 4500.0]
    assert wall.geometry["rotation_deg"] == 90.0
    assert wall.geometry["dimensions"]["Length"] == 8000.0
    assert wall.properties["Pset_WallCommon.FireRating"] == "2HR"
    assert wall.properties["Pset_WallCommon.LoadBearing"] is False


def test_ifc_rooms_and_containment(ifc_v1):
    room = by_tag(ifc_v1, "204")
    assert room.ifc_class == "IfcSpace" and room.room == "204" and room.level == "L02"
    assert room.properties["Qto_SpaceBaseQuantities.NetFloorArea"] == 80.0
    assert room.properties["Pset_SpaceCommon.OccupancyType"] == "Electrical Room"
    assert by_tag(ifc_v1, "D-202A").room == "205"


def test_ifc_revision_differences_are_visible_in_extracted_data(ifc_v1):
    v2 = IfcProvider()
    v2.import_model(IFC_DIR / "architecture_v2.ifc")
    assert len(list(v2.list_elements())) == 20
    old, new = by_tag(ifc_v1, "W-204"), by_tag(v2, "W-204")
    assert old.guid == new.guid and old.geometry["location"][0] == 10000.0 and new.geometry["location"][0] == 10300.0
    assert old.fingerprint() != new.fingerprint()
    assert by_tag(ifc_v1, "W-101").fingerprint() == by_tag(v2, "W-101").fingerprint()
    assert by_tag(v2, "D-202A").room == "204" and by_tag(ifc_v1, "D-202A").room == "205"
    assert by_tag(v2, "204").properties["Pset_SpaceCommon.OccupancyType"] == "Switchgear Room"
    assert by_tag(v2, "W-207") and old.guid in {e.guid for e in v2.list_elements()}


def test_ifc_other_disciplines():
    pytest.importorskip("ifcopenshell")
    structure, mep = IfcProvider(), IfcProvider()
    assert structure.import_model(IFC_DIR / "structure_v1.ifc").element_count == 21
    assert mep.import_model(IFC_DIR / "mep_v1.ifc").element_count == 6
    assert by_tag(structure, "C-B1").geometry["location"][:2] == [10000.0, 0.0]
    assert by_tag(mep, "AHU-301").room == "204"


def test_ifc_garbage_file_is_a_clear_error(tmp_path):
    pytest.importorskip("ifcopenshell")
    path = tmp_path / "bad.ifc"
    path.write_text("ISO-10303-21;\nthis is not a model")
    with pytest.raises(BimError, match="could not be parsed"):
        IfcProvider().import_model(path)


def test_ifc_body_footprint_is_extracted(ifc_v1):
    wall = by_tag(ifc_v1, "W-204").geometry["footprint"]
    assert wall == {"x0": 0.0, "y0": -100.0, "x1": 8000.0, "y1": 100.0, "height": 4000.0}
    column = by_tag(IfcProviderFor("structure_v1.ifc"), "C-A1").geometry["footprint"]
    assert column == {"x0": -200.0, "y0": -200.0, "x1": 200.0, "y1": 200.0, "height": 4000.0}
    assert "footprint" not in by_tag(ifc_v1, "204").geometry  # spaces have no body in the samples


def IfcProviderFor(name):
    provider = IfcProvider()
    provider.import_model(IFC_DIR / name)
    return provider
