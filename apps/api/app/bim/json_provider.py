import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from app.bim.provider import BIMProvider, BimError
from app.bim.types import ElementData, ModelInfo

SCHEMA = "bimguard.elements/1"


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


class JsonProvider(BIMProvider):
    """Structured element lists (quantities, equipment schedules) in the bimguard.elements/1 format."""

    name = "json"
    extensions = (".json",)

    def __init__(self) -> None:
        self._elements: dict[str, ElementData] = {}

    def import_model(self, path: Path) -> ModelInfo:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BimError(f"The JSON file could not be read: {exc}") from exc
        items = raw.get("elements") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            raise BimError(f"Structured JSON models must be an object with an 'elements' list (format {SCHEMA}).")
        self._elements = {}
        for index, item in enumerate(items, start=1):
            element = self._parse(item, index)
            self._elements.setdefault(element.guid, element)
        schema = str(raw.get("schema") or SCHEMA)[:32]
        return ModelInfo(schema=schema, element_count=len(self._elements), application=None)

    @staticmethod
    def _parse(item: Any, index: int) -> ElementData:
        if not isinstance(item, dict):
            raise BimError(f"Element {index}: expected an object.")
        guid = item.get("id") or item.get("guid")
        if not guid:
            raise BimError(f"Element {index}: missing 'id'.")
        if not item.get("class"):
            raise BimError(f"Element {index} ({guid}): missing 'class'.")
        properties, geometry = item.get("properties", {}), item.get("geometry", {})
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise BimError(f"Element {index} ({guid}): 'properties' and 'geometry' must be objects.")
        return ElementData(
            guid=str(guid)[:64], ifc_class=str(item["class"])[:64], name=str(item.get("name") or ""),
            tag=str(item.get("tag") or guid)[:64], level=_text(item.get("level")), room=_text(item.get("room")),
            material=_text(item.get("material")), properties=properties, geometry=geometry,
        )

    def list_elements(self) -> Iterator[ElementData]:
        yield from self._elements.values()

    def get_element(self, guid: str) -> ElementData | None:
        return self._elements.get(guid)


class MockProvider(BIMProvider):
    """In-memory provider for tests and demos; never touches the filesystem."""

    name = "mock"

    def __init__(self, elements: Iterable[ElementData] = ()) -> None:
        self._elements = {e.guid: e for e in elements}

    def import_model(self, path: Path | None = None) -> ModelInfo:
        return ModelInfo(schema="mock", element_count=len(self._elements), application="BIMGuard test double")

    def list_elements(self) -> Iterator[ElementData]:
        yield from self._elements.values()

    def get_element(self, guid: str) -> ElementData | None:
        return self._elements.get(guid)

