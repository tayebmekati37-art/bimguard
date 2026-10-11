"""Small plan-view (2D) geometry helpers for element proximity. Lengths in millimetres."""
import math

Point = tuple[float, float]
Polygon = list[Point]


def footprint_polygon(geometry: dict | None) -> Polygon | None:
    """The element's outline in plan, from its body extent (`footprint`) or, failing that, a rectangle centred on
    its location from Length x Width. Elements with only a location become a point."""
    if not geometry:
        return None
    location = geometry.get("location")
    if not location or len(location) < 2:
        return None
    rotation = math.radians(float(geometry.get("rotation_deg") or 0.0))
    cos, sin = math.cos(rotation), math.sin(rotation)
    footprint = geometry.get("footprint")
    dims = geometry.get("dimensions") or {}
    if footprint:
        local = [(footprint["x0"], footprint["y0"]), (footprint["x1"], footprint["y0"]),
                 (footprint["x1"], footprint["y1"]), (footprint["x0"], footprint["y1"])]
    elif dims.get("Length") and dims.get("Width"):
        hx, hy = dims["Length"] / 2, dims["Width"] / 2
        local = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    else:
        local = [(0.0, 0.0)] * 4
    x0, y0 = float(location[0]), float(location[1])
    return [(x0 + x * cos - y * sin, y0 + x * sin + y * cos) for x, y in local]


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9 and \
        min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1, o2, o3, o4 = _orientation(a, b, c), _orientation(a, b, d), _orientation(c, d, a), _orientation(c, d, b)
    if ((o1 > 1e-9 and o2 < -1e-9) or (o1 < -1e-9 and o2 > 1e-9)) and \
       ((o3 > 1e-9 and o4 < -1e-9) or (o3 < -1e-9 and o4 > 1e-9)):
        return True
    return ((abs(o1) <= 1e-9 and _on_segment(a, b, c)) or (abs(o2) <= 1e-9 and _on_segment(a, b, d)) or
            (abs(o3) <= 1e-9 and _on_segment(c, d, a)) or (abs(o4) <= 1e-9 and _on_segment(c, d, b)))


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_sq))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _inside(p: Point, polygon: Polygon) -> bool:
    inside = False
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def polygon_distance(a: Polygon, b: Polygon) -> float:
    """Shortest distance between two outlines; 0 when they touch or overlap."""
    if any(_inside(p, b) for p in a) or any(_inside(p, a) for p in b):
        return 0.0
    edges_a = [(a[i], a[(i + 1) % len(a)]) for i in range(len(a))]
    edges_b = [(b[i], b[(i + 1) % len(b)]) for i in range(len(b))]
    best = math.inf
    for p, q in edges_a:
        for r, s in edges_b:
            if _segments_intersect(p, q, r, s):
                return 0.0
            best = min(best, _point_segment_distance(p, r, s), _point_segment_distance(q, r, s),
                       _point_segment_distance(r, p, q), _point_segment_distance(s, p, q))
    return round(best, 3)
