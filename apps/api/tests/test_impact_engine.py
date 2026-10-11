import math

import pytest

from app.bim.types import ElementData
from app.engines.change_detection.types import Severity as S
from app.engines.graph import DependencyGraph, Edge, RelationshipType as R
from app.engines.impact import (
    DEFAULT_IMPACT_CONFIG as CFG, ChangedElement, ChangeInput, DocumentInfo, ImpactConfig, analyze_impact, link_elements,
)
from app.engines.impact.geometry import footprint_polygon, polygon_distance
from app.engines.impact.scoring import class_group


# ------------------------------------------------------------------ geometry
def square(x, y, size=10.0):
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


def test_polygon_distance_cases():
    assert polygon_distance(square(0, 0), square(15, 0)) == 5.0           # gap
    assert polygon_distance(square(0, 0), square(10, 0)) == 0.0           # touching edges
    assert polygon_distance(square(0, 0), square(5, 5)) == 0.0            # overlapping
    assert polygon_distance(square(0, 0, 100), square(40, 40, 10)) == 0.0  # contained
    assert polygon_distance(square(0, 0), square(13, 14)) == 5.0          # diagonal 3-4-5
    cross_a = [(0, 5), (20, 5), (20, 6), (0, 6)]
    cross_b = [(10, 0), (11, 0), (11, 20), (10, 20)]
    assert polygon_distance(cross_a, cross_b) == 0.0                      # crossing bars, no vertex inside


def test_footprint_polygon_uses_rotation_location_and_fallbacks():
    wall = {"location": [10300.0, 0.0, 4500.0], "rotation_deg": 90.0,
            "footprint": {"x0": 0.0, "y0": -100.0, "x1": 8000.0, "y1": 100.0, "height": 4000.0}}
    xs = sorted(round(p[0]) for p in footprint_polygon(wall))
    ys = sorted(round(p[1]) for p in footprint_polygon(wall))
    assert xs[0] == 10200 and xs[-1] == 10400 and ys[0] == 0 and ys[-1] == 8000
    centred = footprint_polygon({"location": [100.0, 100.0, 0], "dimensions": {"Length": 40.0, "Width": 20.0}})
    assert min(p[0] for p in centred) == 80 and max(p[1] for p in centred) == 110
    assert footprint_polygon({"location": [5.0, 6.0, 0]}) == [(5.0, 6.0)] * 4
    assert footprint_polygon({}) is None and footprint_polygon(None) is None


def test_demo_wall_to_air_handler_clearance_is_200mm():
    wall_after = {"location": [10300.0, 0.0, 4500.0], "rotation_deg": 90.0,
                  "footprint": {"x0": 0.0, "y0": -100.0, "x1": 8000.0, "y1": 100.0, "height": 4000.0}}
    ahu = {"location": [11800.0, 1000.0, 4500.0], "rotation_deg": 0.0,
           "footprint": {"x0": -1200.0, "y0": -750.0, "x1": 1200.0, "y1": 750.0, "height": 2200.0}}
    assert polygon_distance(footprint_polygon(ahu), footprint_polygon(wall_after)) == pytest.approx(200.0)


# ------------------------------------------------------------------ element linking
def changed(tag="W-204", cls="IfcWall", types=("GEOMETRY_CHANGED",), rooms=(), level="L02", new=None, old=None):
    return ChangedElement(guid=f"g-{tag}", tag=tag, ifc_class=cls, change_types=tuple(types), summary=f"{tag} changed",
                          rooms=frozenset(rooms), level=level, new_geometry=new, old_geometry=old)


def element(tag, cls="Item", room=None, level="L02", props=None, geometry=None):
    return ElementData(guid=f"e-{tag}", ifc_class=cls, name=tag, tag=tag, room=room, level=level,
                       properties=props or {}, geometry=geometry or {})


WALL = {"location": [10300.0, 0.0, 0.0], "rotation_deg": 90.0,
        "footprint": {"x0": 0.0, "y0": -100.0, "x1": 8000.0, "y1": 100.0, "height": 4000.0}}


def test_link_rules():
    ch = [changed(new=WALL, rooms=["204"]), changed("204", "IfcSpace", types=("PARAMETER_CHANGED",))]
    deps = [
        element("W-204", "IfcWall"),                                           # counterpart (same class and tag)
        element("QTO-1", props={"BasedOn": ["W-204", "W-1"]}),                 # reference
        element("NEAR", geometry={"location": [11000.0, 4000.0, 0], "dimensions": {"Length": 400.0, "Width": 400.0}}),
        element("FAR", geometry={"location": [20000.0, 4000.0, 0], "dimensions": {"Length": 400.0, "Width": 400.0}}),
        element("ROOMMATE", room="204"),
        element("OTHERLEVEL", level="L03", geometry={"location": [10500.0, 4000.0, 0], "dimensions": {"Length": 100.0, "Width": 100.0}}),
        element("UNRELATED", room="999"),
    ]
    linked, total = link_elements(ch, deps, CFG)
    by = {a.tag: a for a in linked}
    assert total == 4 and set(by) == {"W-204", "QTO-1", "NEAR", "ROOMMATE"}
    assert by["W-204"].kinds == ("counterpart",) and "Corresponds to Wall W-204" in by["W-204"].reasons[0]
    assert by["QTO-1"].kinds == ("references",)
    assert by["NEAR"].kinds == ("proximity",) and by["NEAR"].distance_mm == pytest.approx(400.0)
    assert by["NEAR"].reasons == ("400 mm from Wall W-204 after the change",)
    assert by["ROOMMATE"].kinds == ("same_room",) and "In room 204" in by["ROOMMATE"].reasons[0]
    assert [a.tag for a in linked] == ["W-204", "QTO-1", "NEAR", "ROOMMATE"]  # strongest rule first


def test_touching_elements_are_reported_as_overlap_and_removed_elements_use_old_position():
    ch = [changed(types=("ELEMENT_REMOVED",), old=WALL, new=None)]
    touching = element("COL", geometry={"location": [10000.0, 4000.0, 0], "footprint": {"x0": -200.0, "y0": -200.0, "x1": 200.0, "y1": 200.0, "height": 1}})
    linked, _ = link_elements(ch, [touching], CFG)
    assert linked[0].distance_mm == 0 and linked[0].reasons == ("Overlaps or touches Wall W-204 after the change",)


def test_parameter_only_changes_do_not_create_proximity_links():
    ch = [changed(types=("PARAMETER_CHANGED",), new=WALL)]
    near = element("NEAR", geometry={"location": [10500.0, 4000.0, 0], "dimensions": {"Length": 100.0, "Width": 100.0}})
    assert link_elements(ch, [near], CFG) == ([], 0)


def test_linking_is_capped_but_counts_everything():
    cfg = ImpactConfig(max_affected_elements=3)
    deps = [element(f"R{i}", room="204") for i in range(10)]
    linked, total = link_elements([changed(rooms=["204"])], deps, cfg)
    assert len(linked) == 3 and total == 10 and [a.tag for a in linked] == ["R0", "R1", "R2"]


# ------------------------------------------------------------------ scoring
def doc(id_, number, discipline, status="approved", revision=1):
    return DocumentInfo(id=id_, number=number, discipline=discipline, status=status, current_revision_number=revision)


def change(change_type="GEOMETRY_CHANGED", severity="MEDIUM", cls="IfcWall", tag="W-204", confidence=0.99):
    return ChangeInput(change_type, severity, confidence, cls, tag, f"{tag} {change_type.lower()}")


def edge(id_, source, target, kind=R.DEPENDS_ON, confidence=1.0, reason=""):
    return Edge(id=id_, source=source, target=target, relationship_type=kind, confidence=confidence, reason=reason)


FACTORY_DOCS = {d.id: d for d in (doc("A", "A-101", "architecture", "in_review", 13), doc("S", "S-201", "structure"),
                                  doc("M", "M-301", "mep"), doc("Q", "Q-101", "quantity"), doc("E", "E-020", "equipment"))}
FACTORY_EDGES = [edge("e1", "S", "A", R.DEPENDS_ON, 0.95, "Structural layout follows the walls"),
                 edge("e2", "M", "A", R.DEPENDS_ON, 0.9, "HVAC follows the layout"),
                 edge("e3", "Q", "A", R.QUANTITY_BASED_ON, 1.0, "Take-offs come from the model"),
                 edge("e4", "E", "M", R.DEPENDS_ON, 0.8, "Equipment coordinated with HVAC")]
FACTORY_CHANGES = [change("GEOMETRY_CHANGED", "MEDIUM", tag="W-204"), change("ELEMENT_ADDED", "MEDIUM", tag="W-207", confidence=0.97)]


def factory(status="approved", changes=None, **kw):
    docs = {k: (v if k == "A" else DocumentInfo(v.id, v.number, v.discipline, status, v.current_revision_number))
            for k, v in FACTORY_DOCS.items()}
    graph = DependencyGraph(docs.keys(), FACTORY_EDGES)
    results = analyze_impact(graph=graph, root=docs["A"], root_revision=13, root_status=kw.pop("root_status", "approved"),
                             documents=docs, changes=FACTORY_CHANGES if changes is None else changes, **kw)
    return {docs[r.document_id].number: r for r in results}


def test_severity_bands():
    assert [CFG.classify(x) for x in (0, 24.9, 25, 49.9, 50, 74.9, 75, 100)] == [
        S.LOW, S.LOW, S.MEDIUM, S.MEDIUM, S.HIGH, S.HIGH, S.CRITICAL, S.CRITICAL]


def test_factory_expansion_scores_and_ranking():
    r = factory()
    assert list(r) == ["S-201", "Q-101", "M-301", "E-020"]  # ranked strongest first
    assert r["S-201"].score == pytest.approx(56.9, abs=0.05) and r["S-201"].severity == S.HIGH
    assert r["Q-101"].score == pytest.approx(53.9, abs=0.05) and r["Q-101"].severity == S.HIGH
    assert r["M-301"].score == pytest.approx(48.7, abs=0.05) and r["M-301"].severity == S.MEDIUM
    assert r["E-020"].score == pytest.approx(23.9, abs=0.05) and r["E-020"].severity == S.LOW
    assert [r[n].direct for n in ("S-201", "E-020")] == [True, False] and r["E-020"].distance == 2


def test_every_factor_is_explained_and_the_formula_adds_up():
    s = factory()["S-201"]
    assert [f.key for f in s.factors] == ["dependency", "change", "propagation", "status"]
    d, c, p, st = (f.value for f in s.factors)
    assert math.isclose(100 * d * c * p * st, s.score, abs_tol=0.2)
    assert (d, c, p, st) == (0.95, 0.63, 1.0, 0.95)
    assert s.formula == "100 x 0.95 x 0.63 x 1.00 x 0.95 = 56.9"
    assert "W-204 geometry_changed" in s.factors[1].explanation and "wall relevance to structure documents = 1.00" in s.factors[1].explanation
    assert "approved (0.95)" in s.factors[3].explanation and "Direct dependency" in s.factors[2].explanation


def test_indirect_impact_decays_and_uses_the_weakest_link():
    e = factory()["E-020"]
    d, c, p, st = (f.value for f in e.factors)
    assert d == 0.8 and p == 0.7 and c == pytest.approx(0.45) and "2 steps away" in e.factors[2].explanation
    assert [s.edge_id for s in e.path] == ["e2", "e4"] and e.first_edge_id == "e2"
    assert "E-020 depends on M-301" in e.reason and "M-301 depends on A-101" in e.reason and "A-101 > M-301 > E-020" in e.reason


def test_confidence_combines_relationship_change_and_distance():
    r = factory()
    assert r["S-201"].confidence == pytest.approx(0.94, abs=0.005)       # 0.95 x 0.99
    assert r["E-020"].confidence == pytest.approx(0.71, abs=0.005)       # weakest relationship 0.8 x change 0.99 x one extra hop 0.9


def test_document_and_revision_status_matter():
    base = factory()["S-201"].score
    assert factory(status="issued")["S-201"].score > base > factory(status="draft")["S-201"].score
    assert factory(root_status="draft")["S-201"].score < base
    assert factory(status="mystery")["S-201"].factors[3].value == pytest.approx(0.7 * 1.0)


def test_the_kind_of_element_changed_matters_per_discipline():
    door = [change("GEOMETRY_CHANGED", "HIGH", cls="IfcDoor", tag="D-1")]
    r = factory(changes=door)
    assert r["S-201"].factors[1].value == pytest.approx(0.85 * 0.4)       # doors barely matter to structure
    assert r["M-301"].factors[1].value == pytest.approx(0.85 * 0.6)
    assert r["Q-101"].factors[1].value == pytest.approx(0.85)             # quantities measure everything
    assert class_group("IfcUnitaryEquipment") == "distribution" and class_group("IfcSpace") == "space"


def test_more_changes_add_a_capped_bonus():
    many = [change(tag=f"W-{i}") for i in range(20)]
    assert factory(changes=many)["S-201"].factors[1].value == pytest.approx(0.6 + 0.15)


def test_score_never_exceeds_100_and_critical_is_reachable():
    graph = DependencyGraph(["A", "S"], [edge("e1", "S", "A", R.DEPENDS_ON, 1.0)])
    docs = {"A": doc("A", "A-1", "architecture", "issued"), "S": doc("S", "S-1", "structure", "issued")}
    removed = [change("ELEMENT_REMOVED", "CRITICAL", "IfcColumn", "C-1", 1.0), change("GEOMETRY_CHANGED", "HIGH", "IfcBeam", "B-1")]
    (result,) = analyze_impact(graph=graph, root=docs["A"], root_revision=2, root_status="issued", documents=docs, changes=removed)
    assert 75 <= result.score <= 100 and result.severity == S.CRITICAL


def test_no_changes_means_no_impact():
    assert factory(changes=[]) == {}


def test_results_are_deterministic():
    assert factory() == factory()


def test_element_links_and_notes_are_attached_to_the_right_document():
    ch = [changed(new=WALL)]
    deps = {"M": [element("AHU-301", geometry={"location": [11800.0, 1000.0, 0], "footprint": {"x0": -1200.0, "y0": -750.0, "x1": 1200.0, "y1": 750.0, "height": 1}})]}
    r = factory(changed_elements=ch, dependent_elements=deps, element_notes={"Q": "Element-level analysis skipped"})
    assert [a.tag for a in r["M-301"].affected_elements] == ["AHU-301"] and r["M-301"].affected_element_count == 1
    assert r["M-301"].affected_elements[0].distance_mm == pytest.approx(200.0)
    assert r["S-201"].affected_elements == () and r["Q-101"].note == "Element-level analysis skipped"


def test_configuration_changes_scores():
    graph = DependencyGraph(FACTORY_DOCS.keys(), FACTORY_EDGES)
    strict = ImpactConfig(propagation_decay=0.1)
    results = analyze_impact(graph=graph, root=FACTORY_DOCS["A"], root_revision=13, root_status="approved",
                             documents=FACTORY_DOCS, changes=FACTORY_CHANGES, config=strict)
    assert next(r for r in results if r.distance == 2).score < 5
    assert strict.to_dict()["propagation_decay"] == 0.1 and "relevance" in strict.to_dict()
