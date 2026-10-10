"""Directed document dependency graph. Pure Python: no database, no web code, no randomness.

Traversal is breadth-first with a visited set, so cycles cannot loop and no document is reported twice.
Each reached document gets its shortest distance and, among equally short paths, the strongest one.
"""
from collections import defaultdict
from collections.abc import Iterable

from app.engines.graph.types import (
    DEFAULT_GRAPH_CONFIG, Edge, Flow, GraphConfig, Impacted, PathStep,
)

_EPS = 1e-12


class DependencyGraph:
    def __init__(self, nodes: Iterable[str], edges: Iterable[Edge], config: GraphConfig = DEFAULT_GRAPH_CONFIG):
        self.config = config
        self.nodes = sorted(set(nodes))
        known = set(self.nodes)
        self.edges = sorted(edges, key=lambda e: e.id)
        # Arcs follow the direction a change travels (provider -> consumer).
        self._downstream: dict[str, list[tuple[str, Edge]]] = defaultdict(list)
        self._upstream: dict[str, list[tuple[str, Edge]]] = defaultdict(list)
        for edge in self.edges:
            for node in (edge.source, edge.target):
                if node not in known:
                    raise ValueError(f"Dependency {edge.id} refers to an unknown document {node}.")
            if edge.source == edge.target:
                raise ValueError(f"Dependency {edge.id} connects a document to itself.")
            for provider, consumer in self._arcs(edge):
                self._downstream[provider].append((consumer, edge))
                self._upstream[consumer].append((provider, edge))
        for adjacency in (self._downstream, self._upstream):
            for arcs in adjacency.values():
                arcs.sort(key=lambda a: (a[0], a[1].id))

    @staticmethod
    def _arcs(edge: Edge) -> list[tuple[str, str]]:
        if edge.flow == Flow.TARGET_TO_SOURCE:
            return [(edge.target, edge.source)]
        if edge.flow == Flow.SOURCE_TO_TARGET:
            return [(edge.source, edge.target)]
        return [(edge.source, edge.target), (edge.target, edge.source)]

    # ------------------------------------------------------------------ traversal
    def impact_from(self, node: str, max_depth: int | None = None) -> list[Impacted]:
        """Every document a change to `node` can reach, ranked strongest first."""
        return self._traverse(node, self._downstream, max_depth)

    def dependencies_of(self, node: str, max_depth: int | None = None) -> list[Impacted]:
        """Every document whose changes can reach `node` (what it relies on), ranked strongest first."""
        return self._traverse(node, self._upstream, max_depth)

    def direct_dependents(self, node: str) -> list[Impacted]:
        return self.impact_from(node, max_depth=1)

    def direct_providers(self, node: str) -> list[Impacted]:
        return self.dependencies_of(node, max_depth=1)

    def impact_radius(self, node: str) -> int:
        """Number of hops to the furthest document a change to `node` can reach (0 if it reaches none)."""
        return max((i.distance for i in self.impact_from(node)), default=0)

    def _traverse(self, root: str, adjacency: dict[str, list[tuple[str, Edge]]],
                  max_depth: int | None) -> list[Impacted]:
        if root not in set(self.nodes):
            raise KeyError(f"Document {root} is not in the graph.")
        distance = {root: 0}
        best: dict[str, tuple[float, tuple[PathStep, ...]]] = {root: (1.0, ())}
        frontier = [root]
        depth = 0
        while frontier and (max_depth is None or depth < max_depth):
            depth += 1
            found: dict[str, tuple[float, tuple[PathStep, ...]]] = {}
            for node in frontier:
                base_strength, base_path = best[node]
                for neighbour, edge in adjacency.get(node, ()):
                    if neighbour in distance:
                        continue  # reached at a shallower depth (or it is the root): never revisit
                    strength = base_strength * edge.strength(self.config)
                    step = PathStep(edge.id, node, neighbour, edge.relationship_type,
                                    edge.strength(self.config), edge.reason)
                    candidate = (strength, base_path + (step,))
                    current = found.get(neighbour)
                    if current is None or self._better(candidate, current):
                        found[neighbour] = candidate
            for neighbour, value in found.items():
                distance[neighbour] = depth
                best[neighbour] = value
            frontier = sorted(found)
        result = [Impacted(n, distance[n], round(best[n][0], 6), best[n][1]) for n in distance if n != root]
        return sorted(result, key=lambda i: (-i.strength, i.distance, i.node))

    @staticmethod
    def _better(candidate, current) -> bool:
        if candidate[0] > current[0] + _EPS:
            return True
        if abs(candidate[0] - current[0]) <= _EPS:
            return tuple(s.edge_id for s in candidate[1]) < tuple(s.edge_id for s in current[1])
        return False

    # ------------------------------------------------------------------ cycles
    def find_cycles(self) -> list[list[str]]:
        """Groups of documents that depend on each other, directly or through others. Symmetric relationships
        (spatially_related_to) are expected to be mutual and are ignored."""
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.provider is not None:
                adjacency[edge.provider].append(edge.consumer)
        index, low, on_stack, stack, counter = {}, {}, set(), [], [0]
        cycles: list[list[str]] = []

        def strongconnect(start: str) -> None:  # iterative Tarjan, safe for deep graphs
            work = [(start, iter(sorted(adjacency.get(start, ()))))]
            index[start] = low[start] = counter[0]
            counter[0] += 1
            stack.append(start)
            on_stack.add(start)
            while work:
                node, children = work[-1]
                advanced = False
                for child in children:
                    if child not in index:
                        index[child] = low[child] = counter[0]
                        counter[0] += 1
                        stack.append(child)
                        on_stack.add(child)
                        work.append((child, iter(sorted(adjacency.get(child, ())))))
                        advanced = True
                        break
                    if child in on_stack:
                        low[node] = min(low[node], index[child])
                if advanced:
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    if len(component) > 1:
                        cycles.append(sorted(component))

        for node in self.nodes:
            if node not in index:
                strongconnect(node)
        return sorted(cycles)
