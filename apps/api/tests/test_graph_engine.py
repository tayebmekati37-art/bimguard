import random

import pytest

from app.engines.graph import DependencyGraph, Edge, GraphConfig, RelationshipType as R, is_stale


def edge(id_, source, target, kind=R.DEPENDS_ON, confidence=1.0, **kw):
    return Edge(id=id_, source=source, target=target, relationship_type=kind, confidence=confidence, **kw)


def nodes(*names):
    return list(names)


def test_depends_on_means_changes_flow_from_target_to_source():
    g = DependencyGraph(nodes("A", "S"), [edge("e1", "S", "A")])  # S depends on A
    assert [i.node for i in g.impact_from("A")] == ["S"]
    assert g.impact_from("S") == []  # changing S does not outdate A
    assert [i.node for i in g.dependencies_of("S")] == ["A"]


def test_affects_flows_from_source_to_target():
    g = DependencyGraph(nodes("A", "M"), [edge("e1", "A", "M", R.AFFECTS)])
    assert [i.node for i in g.impact_from("A")] == ["M"] and g.impact_from("M") == []


def test_direct_and_indirect_impact_with_distance_and_path():
    g = DependencyGraph(nodes("A", "M", "E"), [edge("e1", "M", "A"), edge("e2", "E", "M")])
    impacted = {i.node: i for i in g.impact_from("A")}
    assert impacted["M"].distance == 1 and impacted["M"].direct
    assert impacted["E"].distance == 2 and not impacted["E"].direct
    assert [s.edge_id for s in impacted["E"].path] == ["e1", "e2"]
    assert [(s.from_node, s.to_node) for s in impacted["E"].path] == [("A", "M"), ("M", "E")]
    assert g.impact_radius("A") == 2 and g.impact_radius("E") == 0


def test_circular_dependencies_terminate_and_are_reported():
    g = DependencyGraph(nodes("A", "B", "C"), [edge("e1", "A", "B"), edge("e2", "B", "A"), edge("e3", "C", "B")])
    assert [i.node for i in g.impact_from("A")] == ["B", "C"] or {i.node for i in g.impact_from("A")} == {"B"}
    result = g.impact_from("A")
    assert len({i.node for i in result}) == len(result) and "A" not in {i.node for i in result}
    assert g.find_cycles() == [["A", "B"]]


def test_longer_cycle_and_no_false_positive():
    ring = DependencyGraph(nodes("A", "B", "C"), [edge("1", "B", "A"), edge("2", "C", "B"), edge("3", "A", "C")])
    assert ring.find_cycles() == [["A", "B", "C"]]
    chain = DependencyGraph(nodes("A", "B", "C"), [edge("1", "B", "A"), edge("2", "C", "B")])
    assert chain.find_cycles() == []


def test_symmetric_relationships_flow_both_ways_but_are_not_cycles():
    g = DependencyGraph(nodes("S", "M"), [edge("e1", "S", "M", R.SPATIALLY_RELATED_TO)])
    assert [i.node for i in g.impact_from("S")] == ["M"] and [i.node for i in g.impact_from("M")] == ["S"]
    assert g.find_cycles() == []


def test_diamond_reports_each_document_once_via_strongest_shortest_path():
    #       A
    #   B (strong)  C (weak)
    #       D
    edges = [edge("e1", "B", "A", R.DEPENDS_ON), edge("e2", "C", "A", R.REFERENCES),
             edge("e3", "D", "B", R.DEPENDS_ON), edge("e4", "D", "C", R.DEPENDS_ON)]
    g = DependencyGraph(nodes("A", "B", "C", "D"), edges)
    result = g.impact_from("A")
    assert sorted(i.node for i in result) == ["B", "C", "D"]
    d = next(i for i in result if i.node == "D")
    assert d.distance == 2 and [s.edge_id for s in d.path] == ["e1", "e3"] and d.strength == 1.0


def test_shortest_path_wins_over_a_longer_stronger_one():
    edges = [edge("direct", "D", "A", R.REFERENCES), edge("1", "B", "A"), edge("2", "C", "B"), edge("3", "D", "C")]
    d = next(i for i in DependencyGraph(nodes("A", "B", "C", "D"), edges).impact_from("A") if i.node == "D")
    assert d.distance == 1 and d.strength == 0.3


def test_strength_ranks_structural_over_reference_and_scales_with_confidence():
    edges = [edge("e1", "S", "A", R.DEPENDS_ON, 0.9), edge("e2", "R", "A", R.REFERENCES, 1.0),
             edge("e3", "Q", "A", R.QUANTITY_BASED_ON, 1.0)]
    ranked = DependencyGraph(nodes("A", "S", "R", "Q"), edges).impact_from("A")
    assert [(i.node, i.strength) for i in ranked] == [("Q", 0.9), ("S", 0.9), ("R", 0.3)]


def test_path_strength_is_the_product_of_edge_strengths():
    g = DependencyGraph(nodes("A", "B", "C"), [edge("1", "B", "A", R.DEPENDS_ON, 0.8), edge("2", "C", "B", R.QUANTITY_BASED_ON, 0.5)])
    c = next(i for i in g.impact_from("A") if i.node == "C")
    assert c.strength == pytest.approx(0.8 * 0.45)


def test_custom_weights_are_respected():
    config = GraphConfig(type_weights={**GraphConfig().type_weights, R.REFERENCES: 1.0})
    g = DependencyGraph(nodes("A", "B"), [edge("1", "B", "A", R.REFERENCES)], config)
    assert g.impact_from("A")[0].strength == 1.0


def test_max_depth_limits_traversal():
    g = DependencyGraph(nodes("A", "B", "C", "D"), [edge("1", "B", "A"), edge("2", "C", "B"), edge("3", "D", "C")])
    assert [i.node for i in g.impact_from("A", max_depth=2)] == ["B", "C"]
    assert [i.node for i in g.direct_dependents("A")] == ["B"]
    assert [i.node for i in g.direct_providers("D")] == ["C"]
    assert sorted(i.node for i in g.dependencies_of("D")) == ["A", "B", "C"]


def test_isolated_and_unknown_nodes():
    g = DependencyGraph(nodes("A", "B"), [])
    assert g.impact_from("A") == [] and g.find_cycles() == []
    with pytest.raises(KeyError):
        g.impact_from("Z")


def test_invalid_edges_are_rejected():
    with pytest.raises(ValueError, match="unknown document"):
        DependencyGraph(nodes("A"), [edge("1", "A", "Z")])
    with pytest.raises(ValueError, match="itself"):
        DependencyGraph(nodes("A"), [edge("1", "A", "A")])


def test_results_do_not_depend_on_input_order():
    base = [edge(f"e{i}", f"N{i + 1}", f"N{i}", R.DEPENDS_ON, 1.0 - i * 0.01) for i in range(12)]
    base += [edge("x1", "N5", "N1", R.REFERENCES), edge("x2", "N9", "N3", R.DERIVED_FROM), edge("x3", "N2", "N9")]
    names = [f"N{i}" for i in range(13)]
    expected = DependencyGraph(names, base).impact_from("N0")
    for seed in range(4):
        shuffled = base[:]
        random.Random(seed).shuffle(shuffled)
        assert DependencyGraph(names[::-1], shuffled).impact_from("N0") == expected


def test_large_chain_does_not_recurse():
    count = 3000
    edges = [edge(f"e{i}", f"N{i + 1}", f"N{i}") for i in range(count)]
    g = DependencyGraph([f"N{i}" for i in range(count + 1)], edges)
    assert g.impact_radius("N0") == count and g.find_cycles() == []


def test_staleness_follows_the_provider_revision():
    dep = edge("1", "S", "A", R.DEPENDS_ON, validated_against_revision=12)
    assert not is_stale(dep, 12) and is_stale(dep, 13) and not is_stale(dep, None)
    assert is_stale(edge("2", "S", "A"), 1)  # never validated
    affects = edge("3", "A", "M", R.AFFECTS, validated_against_revision=5)
    assert is_stale(affects, 6) and affects.provider == "A" and affects.consumer == "M"
    assert not is_stale(edge("4", "S", "M", R.SPATIALLY_RELATED_TO, validated_against_revision=1), 9)
