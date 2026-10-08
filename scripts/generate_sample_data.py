#!/usr/bin/env python3
"""Generates the synthetic 'Factory Expansion - Building A' sample data.

Pure standard library: writes IFC4 (STEP) text directly. All data is simulated.
Run from the repo root:  python scripts/generate_sample_data.py
GlobalIds are deterministic, so an element keeps the same id across revisions.
"""
import json
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IFC_DIR = ROOT / "data" / "sample_ifc"
JSON_DIR = ROOT / "data" / "sample_projects" / "factory_expansion"
STOREY_ELEVATION = 4500.0
PROJECT_NAME = "Factory Expansion - Building A"
_B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def ifc_guid(key: str) -> str:
    num = uuid.uuid5(uuid.NAMESPACE_URL, "bimguard:" + key).int
    chars = []
    for _ in range(21):
        chars.append(_B64[num % 64])
        num //= 64
    chars.append(_B64[num])
    return "".join(reversed(chars))


def fmt(x: float) -> str:
    x = round(x, 9)
    if abs(x) < 1e-9:
        x = 0.0
    return f"{x:.6f}".rstrip("0")


def q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def ref(i: int) -> str:
    return f"#{i}"


def refs(ids) -> str:
    return "(" + ",".join(ref(i) for i in ids) + ")"


class Step:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> int:
        self.lines.append(f"#{len(self.lines) + 1}={text};")
        return len(self.lines)


def prop_value(v) -> str:
    if isinstance(v, bool):
        return f"IFCBOOLEAN({'.T.' if v else '.F.'})"
    if isinstance(v, int):
        return f"IFCINTEGER({v})"
    if isinstance(v, float):
        return f"IFCREAL({fmt(v)})"
    return f"IFCLABEL({q(str(v))})"


@dataclass
class Room:
    number: str
    long_name: str
    x0: float
    y0: float
    x1: float
    y1: float
    occupancy: str
    height: float = 4000.0

    @property
    def area(self) -> float:
        return round((self.x1 - self.x0) * (self.y1 - self.y0) / 1e6, 3)


@dataclass
class El:
    key: str
    cls: str
    name: str
    tag: str
    x: float
    y: float
    z: float = 0.0
    rot: float = 0.0
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    center_x: bool = False
    container: str = "storey"
    material: str | None = None
    psets: dict = field(default_factory=dict)
    qto_name: str = ""
    qto: list = field(default_factory=list)  # (kind, name, value)
    obj_type: str | None = None


def box_qto(length, width, height):
    return [("length", "Length", length), ("length", "Width", width), ("length", "Height", height)]


def wall_qto(length, thickness, height):
    return box_qto(length, thickness, height) + [
        ("area", "NetSideArea", round(length * height / 1e6, 3)),
        ("volume", "NetVolume", round(length * thickness * height / 1e9, 3)),
    ]


def build_ifc(filename: str, rooms: list[Room], elements: list[El]) -> str:
    st = Step()
    g = lambda key: q(ifc_guid(f"{filename.split('_v')[0]}:{key}"))  # noqa: E731  (stable per model family)

    origin = st.add("IFCCARTESIANPOINT((0.,0.,0.))")
    zdir = st.add("IFCDIRECTION((0.,0.,1.))")
    xdir = st.add("IFCDIRECTION((1.,0.,0.))")
    world = st.add(f"IFCAXIS2PLACEMENT3D({ref(origin)},{ref(zdir)},{ref(xdir)})")
    o3 = st.add(f"IFCAXIS2PLACEMENT3D({ref(origin)},$,$)")
    ctx = st.add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,{ref(world)},$)")
    body_ctx = st.add(
        f"IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,{ref(ctx)},$,.MODEL_VIEW.,$)")
    u_len = st.add("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)")
    u_area = st.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
    u_vol = st.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
    u_ang = st.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
    units = st.add(f"IFCUNITASSIGNMENT({refs([u_len, u_area, u_vol, u_ang])})")
    project = st.add(f"IFCPROJECT({g('project')},$,{q(PROJECT_NAME)},$,$,$,$,{refs([ctx])},{ref(units)})")

    site_lp = st.add(f"IFCLOCALPLACEMENT($,{ref(world)})")
    site = st.add(f"IFCSITE({g('site')},$,'Site',$,$,{ref(site_lp)},$,$,.ELEMENT.,$,$,$,$,$)")
    bld_lp = st.add(f"IFCLOCALPLACEMENT({ref(site_lp)},{ref(world)})")
    building = st.add(f"IFCBUILDING({g('building')},$,'Building A',$,$,{ref(bld_lp)},$,$,.ELEMENT.,$,$,$)")
    s_pt = st.add(f"IFCCARTESIANPOINT(({fmt(0)},{fmt(0)},{fmt(STOREY_ELEVATION)}))")
    s_ax = st.add(f"IFCAXIS2PLACEMENT3D({ref(s_pt)},$,$)")
    storey_lp = st.add(f"IFCLOCALPLACEMENT({ref(bld_lp)},{ref(s_ax)})")
    storey = st.add(
        f"IFCBUILDINGSTOREY({g('storey')},$,'L02',$,$,{ref(storey_lp)},$,'Level 02',.ELEMENT.,{fmt(STOREY_ELEVATION)})")
    st.add(f"IFCRELAGGREGATES({g('rel-project')},$,$,$,{ref(project)},{refs([site])})")
    st.add(f"IFCRELAGGREGATES({g('rel-site')},$,$,$,{ref(site)},{refs([building])})")
    st.add(f"IFCRELAGGREGATES({g('rel-building')},$,$,$,{ref(building)},{refs([storey])})")

    materials: dict[str, int] = {}

    def placement(x, y, z, rot):
        pt = st.add(f"IFCCARTESIANPOINT(({fmt(x)},{fmt(y)},{fmt(z)}))")
        d = st.add(f"IFCDIRECTION(({fmt(math.cos(math.radians(rot)))},{fmt(math.sin(math.radians(rot)))},0.))")
        ax = st.add(f"IFCAXIS2PLACEMENT3D({ref(pt)},{ref(zdir)},{ref(d)})")
        return st.add(f"IFCLOCALPLACEMENT({ref(storey_lp)},{ref(ax)})")

    def attach(el_id: int, key: str, psets: dict, qto_name: str, qto: list, material: str | None):
        for pname, values in psets.items():
            props = [st.add(f"IFCPROPERTYSINGLEVALUE({q(k)},$,{prop_value(v)},$)") for k, v in values.items()]
            ps = st.add(f"IFCPROPERTYSET({g(key + ':' + pname)},$,{q(pname)},$,{refs(props)})")
            st.add(f"IFCRELDEFINESBYPROPERTIES({g(key + ':rel:' + pname)},$,$,$,{refs([el_id])},{ref(ps)})")
        if qto:
            items = []
            for kind, name, value in qto:
                ent = {"length": "IFCQUANTITYLENGTH", "area": "IFCQUANTITYAREA", "volume": "IFCQUANTITYVOLUME"}[kind]
                items.append(st.add(f"{ent}({q(name)},$,$,{fmt(value)},$)"))
            eq = st.add(f"IFCELEMENTQUANTITY({g(key + ':qto')},$,{q(qto_name)},$,$,{refs(items)})")
            st.add(f"IFCRELDEFINESBYPROPERTIES({g(key + ':rel:qto')},$,$,$,{refs([el_id])},{ref(eq)})")
        if material:
            if material not in materials:
                materials[material] = st.add(f"IFCMATERIAL({q(material)})")
            st.add(f"IFCRELASSOCIATESMATERIAL({g(key + ':rel:mat')},$,$,$,{refs([el_id])},{ref(materials[material])})")

    space_ids: dict[str, int] = {}
    for r in rooms:
        lp = placement(r.x0, r.y0, 0.0, 0.0)
        sid = st.add(
            f"IFCSPACE({g('space:' + r.number)},$,{q(r.number)},$,$,{ref(lp)},$,{q(r.long_name)},.ELEMENT.,.INTERNAL.,$)")
        space_ids[r.number] = sid
        attach(sid, "space:" + r.number,
               {"Pset_SpaceCommon": {"Reference": r.number, "OccupancyType": r.occupancy, "IsExternal": False}},
               "Qto_SpaceBaseQuantities",
               [("length", "Height", r.height), ("area", "NetFloorArea", r.area), ("area", "GrossFloorArea", r.area)],
               None)
    if space_ids:
        st.add(f"IFCRELAGGREGATES({g('rel-spaces')},$,$,$,{ref(storey)},{refs(space_ids.values())})")

    contained: dict[str, list[int]] = {}
    for el in elements:
        lp = placement(el.x, el.y, el.z, el.rot)
        pt2 = st.add(f"IFCCARTESIANPOINT(({fmt(el.length / 2 if el.center_x else 0.0)},0.))")
        ax2 = st.add(f"IFCAXIS2PLACEMENT2D({ref(pt2)},$)")
        prof = st.add(f"IFCRECTANGLEPROFILEDEF(.AREA.,$,{ref(ax2)},{fmt(el.length)},{fmt(el.width)})")
        solid = st.add(f"IFCEXTRUDEDAREASOLID({ref(prof)},{ref(o3)},{ref(zdir)},{fmt(el.height)})")
        rep = st.add(f"IFCSHAPEREPRESENTATION({ref(body_ctx)},'Body','SweptSolid',{refs([solid])})")
        shape = st.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,{refs([rep])})")
        head = f"{g('el:' + el.key)},$,{q(el.name)},$,{q(el.obj_type) if el.obj_type else '$'},{ref(lp)},{ref(shape)},{q(el.tag)}"
        if el.cls == "IFCWALL":
            attrs = f"{head},.STANDARD."
        elif el.cls == "IFCDOOR":
            attrs = f"{head},{fmt(el.height)},{fmt(el.length)},.DOOR.,.SINGLE_SWING_LEFT.,$"
        elif el.cls == "IFCSLAB":
            attrs = f"{head},.FLOOR."
        elif el.cls == "IFCCOLUMN":
            attrs = f"{head},.COLUMN."
        elif el.cls == "IFCBEAM":
            attrs = f"{head},.BEAM."
        elif el.cls == "IFCUNITARYEQUIPMENT":
            attrs = f"{head},.AIRHANDLER."
        elif el.cls == "IFCDUCTSEGMENT":
            attrs = f"{head},.RIGIDSEGMENT."
        else:
            raise ValueError(el.cls)
        el_id = st.add(f"{el.cls}({attrs})")
        attach(el_id, "el:" + el.key, el.psets, el.qto_name, el.qto, el.material)
        contained.setdefault(el.container, []).append(el_id)

    for container, ids in contained.items():
        target = storey if container == "storey" else space_ids[container]
        st.add(f"IFCRELCONTAINEDINSPATIALSTRUCTURE({g('contain:' + container)},$,$,$,{refs(ids)},{ref(target)})")

    header = (
        "ISO-10303-21;\nHEADER;\n"
        "FILE_DESCRIPTION(('ViewDefinition [ReferenceView_V1.2]'),'2;1');\n"
        f"FILE_NAME({q(filename)},{q('2026-10-06T14:00:00')},('BIMGuard sample generator'),('BIMGuard'),"
        "'BIMGuard sample generator','BIMGuard','');\n"
        "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n")
    return header + "\n".join(st.lines) + "\nENDSEC;\nEND-ISO-10303-21;\n"


# ------------------------------------------------------------------ architecture
def architecture(v: int):
    moved = v >= 2
    wx = 10300.0 if moved else 10000.0
    rooms = [
        Room("201", "Assembly Area", 0, 8000, 15000, 16000, "Industrial Assembly"),
        Room("202", "Packaging Area", 15000, 8000, 30000, 16000, "Industrial Packaging"),
        Room("203", "Control Room", 0, 0, wx, 8000, "Control Room"),
        Room("204", "Electrical Room", wx, 0, 20000, 8000, "Switchgear Room" if moved else "Electrical Room"),
        Room("205", "Compressor Room", 20000, 0, 30000, 8000, "Plant Room"),
    ]
    T_EXT, T_INT, H = 300.0, 200.0, 4000.0

    def wall(tag, x, y, rot, length, thick, material, fire, ext, load, obj="Partition"):
        return El(key=f"wall-{tag}", cls="IFCWALL", name=f"Wall {tag}", tag=tag, x=x, y=y, rot=rot,
                  length=length, width=thick, height=H, center_x=True, material=material, obj_type=obj,
                  psets={"Pset_WallCommon": {"Reference": tag, "FireRating": fire, "IsExternal": ext,
                                             "LoadBearing": load}},
                  qto_name="Qto_WallBaseQuantities", qto=wall_qto(length, thick, H))

    def door(tag, x, y, rot, width, room, fire="1HR"):
        return El(key=f"door-{tag}", cls="IFCDOOR", name=f"Door {tag}", tag=tag, x=x, y=y, rot=rot,
                  length=width, width=200.0, height=2100.0, container=room, material="Steel door leaf",
                  psets={"Pset_DoorCommon": {"Reference": tag, "FireRating": fire, "IsExternal": False}},
                  qto_name="Qto_DoorBaseQuantities", qto=[("length", "Width", width), ("length", "Height", 2100.0)])

    ext, cmu, gyp = "Precast concrete panel", "Concrete masonry unit", "Gypsum board partition"
    els = [
        wall("W-101", 0, 0, 0, 30000, T_EXT, ext, "2HR", True, True, "Exterior"),
        wall("W-102", 30000, 0, 90, 16000, T_EXT, ext, "2HR", True, True, "Exterior"),
        wall("W-103", 30000, 16000, 180, 30000, T_EXT, ext, "2HR", True, True, "Exterior"),
        wall("W-104", 0, 16000, 270, 16000, T_EXT, ext, "2HR", True, True, "Exterior"),
        wall("W-203", 20000, 0, 90, 8000, T_INT, cmu, "1HR", False, False),
        wall("W-204", wx, 0, 90, 8000, T_INT, cmu, "2HR", False, False),
        wall("W-205", 0, 8000, 0, 30000, T_INT, gyp, "1HR", False, False),
        wall("W-206", 15000, 8000, 90, 8000, T_INT, gyp, "1HR", False, False),
        door("D-101", 6000, 0, 0, 1800.0, "203", "2HR"),
        door("D-204A", wx, 3500, 90, 1000.0, "203", "2HR"),
        door("D-203A", 20000, 3500, 90, 1000.0, "204"),
        door("D-201A", 5000, 8000, 0, 1000.0, "201"),
        door("D-202A", 12000 if moved else 22000, 8000, 0, 1000.0, "204" if moved else "205"),
        El(key="slab-L02", cls="IFCSLAB", name="Floor slab L02", tag="S-L02", x=15000, y=8000, z=-300.0,
           length=30000, width=16000, height=300.0, material="Reinforced concrete", obj_type="Floor",
           psets={"Pset_SlabCommon": {"Reference": "S-L02", "IsExternal": False, "LoadBearing": True}},
           qto_name="Qto_SlabBaseQuantities", qto=box_qto(30000, 16000, 300)),
    ]
    if moved:
        els.append(wall("W-207", 25000, 0, 90, 4000, T_INT, cmu, "1HR", False, False))
    return rooms, els


# ------------------------------------------------------------------ structure
def structure():
    xs, ys = [0, 10000, 20000, 30000], [0, 8000, 16000]
    els = []
    for xi, x in enumerate(xs):
        for yi, y in enumerate(ys):
            tag = f"C-{'ABCD'[xi]}{yi + 1}"
            els.append(El(key=f"col-{tag}", cls="IFCCOLUMN", name=f"Column {tag}", tag=tag, x=x, y=y,
                          length=400, width=400, height=4000, material="Structural steel S355JR",
                          psets={"Pset_ColumnCommon": {"Reference": "HEB300", "LoadBearing": True,
                                                       "IsExternal": False}},
                          qto_name="Qto_ColumnBaseQuantities", qto=box_qto(400, 400, 4000)))
    for yi, y in enumerate(ys):
        for xi in range(3):
            tag = f"B-{yi + 1}{xi + 1}"
            els.append(El(key=f"beam-{tag}", cls="IFCBEAM", name=f"Beam {tag}", tag=tag, x=xs[xi], y=y, z=3500.0,
                          length=10000, width=300, height=500, center_x=True, material="Structural steel S355JR",
                          psets={"Pset_BeamCommon": {"Reference": "IPE400", "LoadBearing": True,
                                                     "Span": 10000.0}},
                          qto_name="Qto_BeamBaseQuantities", qto=box_qto(10000, 300, 500)))
    return [], els


# ------------------------------------------------------------------ MEP
def mep():
    v1_rooms = {r.number: r for r in architecture(1)[0]}
    rooms = [v1_rooms["204"], v1_rooms["205"]]
    els = [
        El(key="ahu-301", cls="IFCUNITARYEQUIPMENT", name="Air handling unit AHU-301", tag="AHU-301",
           x=10500, y=1000, length=2400, width=1500, height=2200, container="204", material="Galvanised steel",
           psets={"Mep_Design": {"SystemName": "SA-301", "NominalAirflowM3h": 12000.0, "ServiceZone": "204"}},
           qto_name="Qto_UnitaryEquipmentQuantities", qto=box_qto(2400, 1500, 2200)),
        El(key="duct-301-A", cls="IFCDUCTSEGMENT", name="Supply duct DUCT-301-A", tag="DUCT-301-A", x=12900,
           y=1750, z=2800, length=7600, width=600, height=400, center_x=True, container="204",
           material="Galvanised steel",
           psets={"Mep_Design": {"SystemName": "SA-301", "NominalAirflowM3h": 12000.0}},
           qto_name="Qto_DuctSegmentBaseQuantities", qto=box_qto(7600, 600, 400)),
        El(key="duct-301-B", cls="IFCDUCTSEGMENT", name="Supply duct DUCT-301-B", tag="DUCT-301-B", x=20500,
           y=1750, z=2800, length=5000, width=600, height=400, center_x=True, container="205",
           material="Galvanised steel",
           psets={"Mep_Design": {"SystemName": "SA-301", "NominalAirflowM3h": 6000.0}},
           qto_name="Qto_DuctSegmentBaseQuantities", qto=box_qto(5000, 600, 400)),
        El(key="duct-301-C", cls="IFCDUCTSEGMENT", name="Return duct DUCT-301-C", tag="DUCT-301-C", x=12900,
           y=2900, z=2800, length=7600, width=500, height=400, center_x=True, container="204",
           material="Galvanised steel",
           psets={"Mep_Design": {"SystemName": "RA-301", "NominalAirflowM3h": 11000.0}},
           qto_name="Qto_DuctSegmentBaseQuantities", qto=box_qto(7600, 500, 400)),
    ]
    return rooms, els


# ------------------------------------------------------------------ JSON models
def json_models():
    rooms, walls = architecture(1)
    wall_els = [e for e in walls if e.cls == "IFCWALL"]
    door_els = [e for e in walls if e.cls == "IFCDOOR"]
    ext = [e for e in wall_els if e.psets["Pset_WallCommon"]["IsExternal"]]
    src = {"document": "A-101", "revision": 12}

    def item(id_, name, value, unit, based_on):
        return {"id": id_, "class": "QuantityItem", "name": name, "level": "L02", "room": None,
                "properties": {"Quantity": round(value, 3), "Unit": unit, "SourceDocument": "A-101",
                               "SourceRevision": 12, "BasedOn": based_on}, "geometry": {}}

    qto = {
        "schema": "bimguard.elements/1",
        "model": {"name": "Q-101 Quantity take-off, Level 02", "source_documents": [src],
                  "note": "Simulated sample data"},
        "elements": [
            item("QTO-WALL-LEN-EXT", "Exterior wall length", sum(e.length for e in ext) / 1000, "m",
                 [e.tag for e in ext]),
            item("QTO-WALL-AREA", "Total net wall side area", sum(e.length * e.height for e in wall_els) / 1e6,
                 "m2", [e.tag for e in wall_els]),
            item("QTO-WALL-VOL", "Total wall volume",
                 sum(e.length * e.width * e.height for e in wall_els) / 1e9, "m3", [e.tag for e in wall_els]),
            item("QTO-DOOR-COUNT", "Door count", len(door_els), "no", [e.tag for e in door_els]),
            item("QTO-FLOOR-AREA", "Net floor area, Level 02", sum(r.area for r in rooms), "m2",
                 [r.number for r in rooms]),
            item("QTO-ROOM-204-AREA", "Room 204 net floor area",
                 next(r.area for r in rooms if r.number == "204"), "m2", ["204"]),
        ],
    }

    def equip(id_, name, x, y, room, dims, props):
        return {"id": id_, "class": "Equipment", "name": name, "level": "L02", "room": room,
                "properties": {**props, "SourceDocument": "A-101", "SourceRevision": 12},
                "geometry": {"location": [x, y, STOREY_ELEVATION], "rotation_deg": 0.0,
                             "dimensions": dims}}

    equipment = {
        "schema": "bimguard.elements/1",
        "model": {"name": "E-020 Equipment schedule, Level 02", "source_documents": [src],
                  "note": "Simulated sample data"},
        "elements": [
            equip("CMP-020", "Screw compressor CMP-020", 27000, 3000, "205",
                  {"Length": 2600, "Width": 1400, "Height": 1900}, {"PowerKW": 55.0, "Manufacturer": "Generic"}),
            equip("RCV-021", "Air receiver RCV-021", 27000, 6200, "205",
                  {"Length": 1200, "Width": 1200, "Height": 2400}, {"VolumeLitres": 1000.0}),
            equip("SWG-040", "Switchgear SWG-040", 11000, 6500, "204",
                  {"Length": 2000, "Width": 800, "Height": 2200}, {"PowerKW": 0.0, "Voltage": "400V"}),
        ],
    }
    return qto, equipment


def main() -> None:
    IFC_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    for v in (1, 2):
        rooms, els = architecture(v)
        (IFC_DIR / f"architecture_v{v}.ifc").write_text(build_ifc(f"architecture_v{v}.ifc", rooms, els), "utf-8", newline="\n")
    rooms, els = structure()
    (IFC_DIR / "structure_v1.ifc").write_text(build_ifc("structure_v1.ifc", rooms, els), "utf-8", newline="\n")
    rooms, els = mep()
    (IFC_DIR / "mep_v1.ifc").write_text(build_ifc("mep_v1.ifc", rooms, els), "utf-8", newline="\n")
    qto, equipment = json_models()
    (JSON_DIR / "quantity_v1.json").write_text(json.dumps(qto, indent=2) + "\n", "utf-8", newline="\n")
    (JSON_DIR / "equipment_v1.json").write_text(json.dumps(equipment, indent=2) + "\n", "utf-8", newline="\n")
    print("Sample data written to", IFC_DIR.parent)


if __name__ == "__main__":
    main()
