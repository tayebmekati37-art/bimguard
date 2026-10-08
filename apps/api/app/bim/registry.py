from app.bim.ifc_provider import IfcProvider
from app.bim.json_provider import JsonProvider
from app.bim.provider import BIMProvider

_PROVIDERS: tuple[type[BIMProvider], ...] = (IfcProvider, JsonProvider)


def provider_for(extension: str) -> BIMProvider | None:
    """Returns a fresh provider for a file extension, or None if the type carries no model data."""
    ext = extension.lower()
    for cls in _PROVIDERS:
        if ext in cls.extensions:
            return cls()
    return None
