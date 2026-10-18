"""Interoperability helpers.

Three operations:

1. Export the BimElement rows of one revision as bimguard.elements/1 JSON.
2. Round-trip verify: export, re-parse with JsonProvider, diff against the
   database. This proves that the canonical JSON format is lossless for the
   element data we actually store.
3. Source verify: re-read the uploaded file with the appropriate provider
   and compare the element GUID set with what is stored. This proves that
   the stored extraction agrees with the uploaded file.

What this module deliberately does NOT do: write IFC, write BCF, or claim
any format compliance beyond what the parsers already provide.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.bim.ifc_provider import IfcProvider
from app.bim.json_provider import SCHEMA, JsonProvider
from app.bim.provider import BimError, BimUnavailableError
from app.models.bim import BimElement
from app.models.document import DocumentRevision
from app.services import storage

log = logging.getLogger("bimguard.interop")

# Tag is skipped because JsonProvider falls back to the GUID when tag is
# empty, so an empty source tag would always appear to mismatch. All other
# comparable fields round-trip cleanly through bimguard.elements/1.
_COMPARE_FIELDS = ("ifc_class", "name", "level", "room", "material")


# ------------------------------------------------------------------ export
def elements_to_dict(elements: list[BimElement]) -> dict[str, Any]:
    """Serialize BimElement rows into the bimguard.elements/1 document shape."""
    return {
        "schema": SCHEMA,
        "elements": [
            {
                "id": e.guid,
                "class": e.ifc_class,
                "name": e.name,
                "tag": e.tag,
                "level": e.level,
                "room": e.room,
                "material": e.material,
                "properties": dict(e.properties or {}),
                "geometry": dict(e.geometry or {}),
            }
            for e in elements
        ],
    }


def export_revision(db: Session, revision: DocumentRevision) -> dict[str, Any]:
    rows = list(db.scalars(
        select(BimElement).where(BimElement.revision_id == revision.id).order_by(BimElement.guid)
    ))
    return elements_to_dict(rows)


# ------------------------------------------------------------------ round-trip
@dataclass
class RoundTripReport:
    revision_id: str
    element_count: int
    matches: int
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    mismatches: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra and not self.mismatches


def verify_round_trip(db: Session, revision: DocumentRevision) -> RoundTripReport:
    """Export -> re-parse through JsonProvider -> diff against the source rows."""
    export = export_revision(db, revision)
    provider = JsonProvider()

    fd, tmp_path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(export, fh)
        provider.import_model(Path(tmp_path))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    parsed = {e.guid: e for e in provider.list_elements()}
    source = list(db.scalars(select(BimElement).where(BimElement.revision_id == revision.id)))
    source_guids = {e.guid for e in source}
    parsed_guids = set(parsed)
    missing = sorted(source_guids - parsed_guids)
    extra = sorted(parsed_guids - source_guids)

    mismatches: list[dict] = []
    for row in source:
        p = parsed.get(row.guid)
        if p is None:
            continue
        diffs: dict[str, dict] = {}
        for name in _COMPARE_FIELDS:
            sv = getattr(row, name)
            pv = getattr(p, name)
            if sv != pv:
                diffs[name] = {"source": sv, "parsed": pv}
        if diffs:
            mismatches.append({"guid": row.guid, "fields": diffs})

    return RoundTripReport(
        revision_id=revision.id,
        element_count=len(source),
        matches=len(source) - len(missing) - len(mismatches),
        missing=missing,
        extra=extra,
        mismatches=mismatches,
    )


# ------------------------------------------------------------------ source verification
@dataclass
class SourceVerificationReport:
    revision_id: str
    source_format: str
    ok: bool
    reason: str = ""
    parsed_element_count: int = 0
    stored_element_count: int = 0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


def _skip(revision: DocumentRevision, fmt: str, reason: str) -> SourceVerificationReport:
    return SourceVerificationReport(
        revision_id=revision.id, source_format=fmt, ok=False, reason=reason
    )


def verify_source(db: Session, revision: DocumentRevision) -> SourceVerificationReport:
    """Re-read the uploaded file and compare its element GUIDs with what is stored."""
    ext = "." + revision.original_filename.rsplit(".", 1)[-1].lower() if "." in revision.original_filename else ""
    fmt = ext.lstrip(".") or "unknown"

    if revision.extraction_status != "ok":
        return _skip(revision, fmt, f"Extraction status is '{revision.extraction_status}', not 'ok'.")

    # Check the format first, so unsupported files never touch the storage layer.
    if ext not in (".ifc", ".json"):
        return _skip(revision, fmt, f"Source format '{fmt}' cannot be re-parsed by any provider.")

    # storage.resolve_stored raises HTTPException(404) when the file is not
    # on disk. Catch it alongside the filesystem errors so a missing file
    # becomes a graceful skip rather than a route-level 404.
    try:
        path = storage.resolve_stored(revision.file_path)
    except HTTPException as exc:
        return _skip(revision, fmt, f"Stored file path is invalid: {exc.detail}")
    except (FileNotFoundError, ValueError, OSError) as exc:
        return _skip(revision, fmt, f"Stored file path is invalid: {exc}")

    if not Path(path).exists():
        return _skip(revision, fmt, "Stored file is missing on disk.")

    if ext == ".ifc":
        provider = IfcProvider()
        try:
            provider.import_model(Path(path))
        except BimUnavailableError as exc:
            return _skip(revision, fmt, f"IFC support unavailable: {exc}")
        except BimError as exc:
            return _skip(revision, fmt, f"Re-parse failed: {exc}")
    else:
        provider = JsonProvider()
        try:
            provider.import_model(Path(path))
        except BimError as exc:
            return _skip(revision, fmt, f"Re-parse failed: {exc}")

    parsed_guids = {e.guid for e in provider.list_elements()}
    stored_rows = list(db.scalars(select(BimElement).where(BimElement.revision_id == revision.id)))
    stored_guids = {r.guid for r in stored_rows}
    missing = sorted(stored_guids - parsed_guids)
    extra = sorted(parsed_guids - stored_guids)
    ok = not missing and not extra
    return SourceVerificationReport(
        revision_id=revision.id,
        source_format=fmt,
        ok=ok,
        reason="" if ok else f"{len(missing)} stored-only, {len(extra)} parsed-only.",
        parsed_element_count=len(parsed_guids),
        stored_element_count=len(stored_guids),
        missing=missing[:50],
        extra=extra[:50],
    )