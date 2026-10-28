"""BCF XSD validation (M29).

Validates BCF XML emitted by app/services/bcf.py against the schemas in
app/services/bcf_xsd/.

IMPORTANT: these schemas describe BIMGuard's subset of BCF, not the full
buildingSMART BCF 2.1 schemas. Passing validation means "matches what
BIMGuard promises to produce," not "conforms to BCF 2.1 in its entirety."
See docs/architecture/bcf.md.

Schemas are compiled once at first use and cached. Compilation happens
under a lock so concurrent requests do not race.
"""
from __future__ import annotations

import io
import logging
import threading
import zipfile
from pathlib import Path

from lxml import etree

log = logging.getLogger("bimguard.bcf_validate")

_SCHEMA_DIR = Path(__file__).resolve().parent / "bcf_xsd"
_CACHE: dict[str, etree.XMLSchema] = {}
_LOCK = threading.Lock()


class BCFValidationError(Exception):
    """Raised when BCF export produces XML that does not match the subset schema."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            f"{len(violations)} schema violation(s): " + "; ".join(violations[:3])
            + ("…" if len(violations) > 3 else "")
        )


def _load(schema_name: str) -> etree.XMLSchema:
    with _LOCK:
        if schema_name in _CACHE:
            return _CACHE[schema_name]
        path = _SCHEMA_DIR / schema_name
        if not path.exists():
            raise FileNotFoundError(f"schema not found: {path}")
        doc = etree.parse(str(path))
        schema = etree.XMLSchema(doc)
        _CACHE[schema_name] = schema
        return schema


def _validate(xml_bytes: bytes, schema_name: str, label: str) -> list[str]:
    schema = _load(schema_name)
    try:
        doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as e:
        return [f"{label}: XML parse error: {e}"]
    if schema.validate(doc):
        return []
    return [f"{label}: {err.message}" for err in schema.error_log]


def validate_version(xml_bytes: bytes) -> list[str]:
    return _validate(xml_bytes, "bcf.version.xsd", "bcf.version")


def validate_markup(xml_bytes: bytes) -> list[str]:
    return _validate(xml_bytes, "markup.xsd", "markup.bcf")


def validate_viewpoint(xml_bytes: bytes) -> list[str]:
    return _validate(xml_bytes, "viewpoint.xsd", "viewpoint.bcfv")


def validate_bcf_zip(data: bytes) -> list[str]:
    """Validate every XML file in a BCF ZIP. Returns violation list."""
    violations: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if "bcf.version" not in names:
                violations.append("missing required file: bcf.version")
            for name in names:
                content = zf.read(name)
                if name == "bcf.version":
                    violations.extend(validate_version(content))
                elif name.endswith("markup.bcf"):
                    violations.extend(validate_markup(content))
                elif name.endswith("viewpoint.bcfv"):
                    violations.extend(validate_viewpoint(content))
    except zipfile.BadZipFile as e:
        violations.append(f"not a valid ZIP: {e}")
    return violations