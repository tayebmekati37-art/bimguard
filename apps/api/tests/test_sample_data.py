"""Structural checks of the generated sample files. No third-party dependencies needed."""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
IFC_DIR = REPO / "data" / "sample_ifc"
JSON_DIR = REPO / "data" / "sample_projects" / "factory_expansion"

ARITY = {
    "IFCPROJECT": 9, "IFCSITE": 14, "IFCBUILDING": 12, "IFCBUILDINGSTOREY": 10, "IFCSPACE": 11,
    "IFCWALL": 9, "IFCDOOR": 13, "IFCSLAB": 9, "IFCCOLUMN": 9, "IFCBEAM": 9,
    "IFCUNITARYEQUIPMENT": 9, "IFCDUCTSEGMENT": 9, "IFCPROPERTYSET": 5, "IFCPROPERTYSINGLEVALUE": 4,
    "IFCRELDEFINESBYPROPERTIES": 6, "IFCRELCONTAINEDINSPATIALSTRUCTURE": 6, "IFCRELAGGREGATES": 6,
    "IFCRELASSOCIATESMATERIAL": 6, "IFCELEMENTQUANTITY": 6, "IFCLOCALPLACEMENT": 2,
    "IFCEXTRUDEDAREASOLID": 4, "IFCRECTANGLEPROFILEDEF": 5, "IFCAXIS2PLACEMENT3D": 3,
    "IFCAXIS2PLACEMENT2D": 2, "IFCSHAPEREPRESENTATION": 4, "IFCPRODUCTDEFINITIONSHAPE": 3,
}
EXPECTED_COUNTS = {  # products (IfcElement + IfcSpace)
    "architecture_v1.ifc": 19, "architecture_v2.ifc": 20, "structure_v1.ifc": 21, "mep_v1.ifc": 6,
}
PRODUCTS = {"IFCSPACE", "IFCWALL", "IFCDOOR", "IFCSLAB", "IFCCOLUMN", "IFCBEAM",
            "IFCUNITARYEQUIPMENT", "IFCDUCTSEGMENT"}


def split_top_level(args: str) -> list[str]:
    parts, depth, current, in_str = [], 0, "", False
    i = 0
    while i < len(args):
        ch = args[i]
        if in_str:
            current += ch
            if ch == "'":
                if i + 1 < len(args) and args[i + 1] == "'":
                    current += "'"
                    i += 1
                else:
                    in_str = False
        elif ch == "'":
            in_str = True
            current += ch
        elif ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
        i += 1
    parts.append(current)
    return parts


def parse(path: Path):
    text = path.read_text("utf-8")
    assert text.startswith("ISO-10303-21;") and text.rstrip().endswith("END-ISO-10303-21;")
    data = text.split("DATA;", 1)[1].split("ENDSEC;", 1)[0]
    entities = {}
    for line in data.strip().splitlines():
        m = re.fullmatch(r"#(\d+)=([A-Z0-9_]+)\((.*)\);", line.strip())
        assert m, f"Unparseable line: {line[:80]}"
        entities[int(m.group(1))] = (m.group(2), m.group(3))
    return entities


@pytest.mark.parametrize("name", sorted(EXPECTED_COUNTS))
def test_ifc_structure(name):
    entities = parse(IFC_DIR / name)
    for eid, (cls, args) in entities.items():
        for target in re.findall(r"#(\d+)", re.sub(r"'(?:[^']|'')*'", "''", args)):
            assert int(target) in entities, f"#{eid} {cls} references missing #{target}"
        if cls in ARITY:
            assert len(split_top_level(args)) == ARITY[cls], f"#{eid} {cls} has wrong attribute count"
    products = [e for e in entities.values() if e[0] in PRODUCTS]
    assert len(products) == EXPECTED_COUNTS[name]
    guids = [split_top_level(a)[0] for c, a in entities.values() if c in PRODUCTS]
    assert len(set(guids)) == len(guids)
    assert all(re.fullmatch(r"'[0-9A-Za-z_$]{22}'", g) for g in guids)


def test_guids_are_stable_between_revisions():
    def guids(name):
        out = {}
        for cls, args in parse(IFC_DIR / name).values():
            if cls in PRODUCTS:
                parts = split_top_level(args)
                out[parts[2]] = parts[0]
        return out
    v1, v2 = guids("architecture_v1.ifc"), guids("architecture_v2.ifc")
    assert all(v2[name] == guid for name, guid in v1.items())
    assert set(v2) - set(v1) == {"'Wall W-207'"}


def test_json_models_follow_schema():
    for name in ("quantity_v1.json", "quantity_v2.json", "equipment_v1.json"):
        doc = json.loads((JSON_DIR / name).read_text("utf-8"))
        assert doc["schema"] == "bimguard.elements/1"
        assert len({e["id"] for e in doc["elements"]}) == len(doc["elements"])
        assert all(e["id"] and e["class"] for e in doc["elements"])


def test_quantity_v2_matches_architecture_v2():
    def items(name):
        return {e["id"]: e for e in json.loads((JSON_DIR / name).read_text("utf-8"))["elements"]}
    v1, v2 = items("quantity_v1.json"), items("quantity_v2.json")
    assert v1["QTO-ROOM-204-AREA"]["properties"]["Quantity"] == 80.0 and v2["QTO-ROOM-204-AREA"]["properties"]["Quantity"] == 77.6
    assert "W-207" not in v1["QTO-WALL-AREA"]["properties"]["BasedOn"] and "W-207" in v2["QTO-WALL-AREA"]["properties"]["BasedOn"]
    assert v2["QTO-WALL-AREA"]["properties"]["SourceRevision"] == 13 and v1["QTO-WALL-AREA"]["properties"]["SourceRevision"] == 12
    assert v2["QTO-FLOOR-AREA"]["properties"]["Quantity"] == 480.0
