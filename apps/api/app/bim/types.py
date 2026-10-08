import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelInfo:
    schema: str
    element_count: int
    application: str | None = None
    unit: str = "mm"


@dataclass(frozen=True)
class ElementData:
    """Provider-neutral element. Lengths are millimetres; geometry holds
    {"location": [x, y, z], "rotation_deg": float, "dimensions": {...}}."""

    guid: str
    ifc_class: str
    name: str = ""
    tag: str = ""
    level: str | None = None
    room: str | None = None
    material: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Stable hash of everything except the id; equal fingerprints mean 'unchanged'."""
        payload = {"c": self.ifc_class, "n": self.name, "t": self.tag, "l": self.level, "r": self.room,
                   "m": self.material, "p": self.properties, "g": self.geometry}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode()).hexdigest()
