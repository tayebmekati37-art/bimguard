from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from app.bim.types import ElementData, ModelInfo


class BimError(Exception):
    """A model could not be read. The message is safe to show to users."""


class BimUnavailableError(BimError):
    """A provider's optional dependency or service is not available."""


class BIMProvider(ABC):
    """Reads a BIM model into provider-neutral ElementData.

    Implementations: IfcProvider (open IFC via IfcOpenShell), JsonProvider (structured sample data),
    MockProvider (tests). An Autodesk Platform Services adapter can implement the same interface later.
    """

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def import_model(self, path: Path) -> ModelInfo: ...

    @abstractmethod
    def list_elements(self) -> Iterator[ElementData]: ...

    def get_element(self, guid: str) -> ElementData | None:
        return next((e for e in self.list_elements() if e.guid == guid), None)

    def get_properties(self, guid: str) -> dict:
        return self._require(guid).properties

    def get_geometry(self, guid: str) -> dict:
        return self._require(guid).geometry

    def _require(self, guid: str) -> ElementData:
        element = self.get_element(guid)
        if element is None:
            raise KeyError(f"Element {guid} is not in this model.")
        return element
