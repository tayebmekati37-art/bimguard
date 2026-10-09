import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.bim.provider import BIMProvider, BimError, BimUnavailableError
from app.bim.types import ElementData, ModelInfo

_DIMENSION_KEYS = ("Length", "Width", "Height", "Depth")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _parent(entity: Any) -> Any:
    for rel in getattr(entity, "ContainedInStructure", None) or ():
        return rel.RelatingStructure
    for rel in getattr(entity, "Decomposes", None) or ():
        return rel.RelatingObject
    return None


class IfcProvider(BIMProvider):
    """IFC reader built on IfcOpenShell. Extracts attributes, property sets, quantities, placement and
    spatial containment. It does not tessellate geometry: location, rotation and quantity-based
    dimensions are what change detection compares."""

    name = "ifc"
    extensions = (".ifc",)

    def __init__(self) -> None:
        self._model: Any = None
        self._products: list[Any] = []
        self._mm_per_unit = 1.0

    def import_model(self, path: Path) -> ModelInfo:
        try:
            import ifcopenshell
            import ifcopenshell.util.element as util_element
            import ifcopenshell.util.placement as util_placement
            import ifcopenshell.util.unit as util_unit
        except ImportError as exc:
            raise BimUnavailableError(
                "IFC support needs the 'ifcopenshell' package. Install it with: pip install ifcopenshell") from exc
        self._util_element, self._util_placement = util_element, util_placement
        try:
            self._model = ifcopenshell.open(str(path))
        except Exception as exc:  # parser raises several exception types
            raise BimError(f"The IFC file could not be parsed: {exc}") from exc
        self._mm_per_unit = float(util_unit.calculate_unit_scale(self._model)) * 1000.0
        self._products = [e for e in self._model.by_type("IfcElement") if not e.is_a("IfcOpeningElement")]
        self._products += list(self._model.by_type("IfcSpace"))
        return ModelInfo(schema=str(self._model.schema), element_count=len(self._products), unit="mm")

    def list_elements(self) -> Iterator[ElementData]:
        for entity in self._products:
            yield self._convert(entity)

    def get_element(self, guid: str) -> ElementData | None:
        try:
            entity = self._model.by_guid(guid)
        except RuntimeError:
            return None
        return self._convert(entity) if entity in self._products else None

    def _convert(self, entity: Any) -> ElementData:
        properties: dict[str, Any] = {}
        dimensions: dict[str, float] = {}
        for pset_name, values in self._util_element.get_psets(entity).items():
            is_quantity_set = pset_name.startswith("Qto_")
            for key, value in values.items():
                if key == "id":
                    continue
                if is_quantity_set and key in _DIMENSION_KEYS and isinstance(value, (int, float)):
                    dimensions[key] = round(float(value) * self._mm_per_unit, 3)
                else:
                    properties[f"{pset_name}.{key}"] = _jsonable(value)
        for attr in ("LongName", "ObjectType", "PredefinedType"):
            value = getattr(entity, attr, None)
            if value:
                properties[f"Attributes.{attr}"] = str(value)
        for attr, key in (("OverallWidth", "Width"), ("OverallHeight", "Height")):
            value = getattr(entity, attr, None)
            if value is not None and key not in dimensions:
                dimensions[key] = round(float(value) * self._mm_per_unit, 3)

        level, room = self._spatial(entity)
        name = entity.Name or ""
        tag = getattr(entity, "Tag", None) or ""
        if entity.is_a("IfcSpace"):
            tag = entity.Name or ""
            name = f"{entity.Name or ''} {getattr(entity, 'LongName', None) or ''}".strip()

        materials = [m.Name for m in self._util_element.get_materials(entity) if getattr(m, "Name", None)]
        return ElementData(
            guid=entity.GlobalId, ifc_class=entity.is_a(), name=name, tag=str(tag), level=level, room=room,
            material=", ".join(dict.fromkeys(materials)) or None, properties=properties,
            geometry=self._geometry(entity, dimensions),
        )

    def _geometry(self, entity: Any, dimensions: dict[str, float]) -> dict[str, Any]:
        geometry: dict[str, Any] = {}
        if entity.ObjectPlacement is not None:
            m = self._util_placement.get_local_placement(entity.ObjectPlacement)
            geometry["location"] = [round(float(m[i][3]) * self._mm_per_unit, 3) for i in range(3)]
            rotation = round(math.degrees(math.atan2(float(m[1][0]), float(m[0][0]))) % 360, 3) % 360
            geometry["rotation_deg"] = rotation + 0.0
        if dimensions:
            geometry["dimensions"] = dimensions
        footprint = self._footprint(entity)
        if footprint:
            geometry["footprint"] = footprint
        return geometry

    def _footprint(self, entity: Any) -> dict[str, float] | None:
        """Local-coordinate extent of a rectangular extruded body (walls, columns, beams, doors,
        equipment). Used for the 2D plan view and body-size change detection. Other body types give None."""
        try:
            representation = entity.Representation
            if representation is None:
                return None
            for shape in representation.Representations or ():
                if shape.RepresentationIdentifier != "Body":
                    continue
                for item in shape.Items or ():
                    if not item.is_a("IfcExtrudedAreaSolid") or not item.SweptArea.is_a("IfcRectangleProfileDef"):
                        continue
                    profile, mm = item.SweptArea, self._mm_per_unit
                    px = py = 0.0
                    if profile.Position is not None:
                        px, py = (float(c) for c in profile.Position.Location.Coordinates[:2])
                    hx, hy = float(profile.XDim) / 2, float(profile.YDim) / 2
                    return {"x0": round((px - hx) * mm, 3), "y0": round((py - hy) * mm, 3),
                            "x1": round((px + hx) * mm, 3), "y1": round((py + hy) * mm, 3),
                            "height": round(float(item.Depth) * mm, 3)}
        except (AttributeError, TypeError, ValueError):
            return None
        return None

    @staticmethod
    def _spatial(entity: Any) -> tuple[str | None, str | None]:
        level = room = None
        if entity.is_a("IfcSpace"):
            room = entity.Name
        current = entity
        for _ in range(10):
            parent = _parent(current)
            if parent is None:
                break
            if parent.is_a("IfcSpace") and room is None:
                room = parent.Name
            if parent.is_a("IfcBuildingStorey"):
                level = parent.Name
                break
            current = parent
        return level, room
