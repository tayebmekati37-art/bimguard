import logging
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.bim.provider import BimError
from app.bim.registry import provider_for
from app.bim.types import ElementData
from app.models.bim import BimElement
from app.models.document import DocumentRevision, ExtractionStatus
from app.services import audit, storage

log = logging.getLogger("bimguard.extraction")
BATCH_SIZE = 1000


def _row(revision_id: str, element: ElementData) -> BimElement:
    return BimElement(
        revision_id=revision_id, guid=element.guid, ifc_class=element.ifc_class, name=element.name[:255],
        tag=element.tag[:64], level=element.level, room=element.room, material=element.material,
        properties=element.properties, geometry=element.geometry, fingerprint=element.fingerprint(),
    )


def _finish(db: Session, revision_id: str, status: ExtractionStatus, message: str,
            count: int | None = None, schema: str | None = None) -> None:
    revision = db.get(DocumentRevision, revision_id)
    if revision is None:
        return
    revision.extraction_status = status.value
    revision.extraction_message = message
    revision.element_count = count
    revision.model_schema = schema
    audit.record(
        db, user=None, action="revision.extracted" if status == ExtractionStatus.OK else f"revision.extraction_{status.value}",
        entity_type="revision", entity_id=revision.id, project_id=revision.document.project_id,
        detail={"document_number": revision.document.document_number, "revision": revision.revision_number,
                "elements": count, "message": message},
    )
    db.commit()


def extract_revision(session_factory: sessionmaker, revision_id: str) -> None:
    """Parses a revision's model file and stores its elements. Runs as a background task and
    never raises: the outcome is recorded on the revision."""
    with session_factory() as db:
        revision = db.get(DocumentRevision, revision_id)
        if revision is None:
            return
        provider = provider_for(Path(revision.file_path).suffix)
        if provider is None:
            _finish(db, revision_id, ExtractionStatus.UNSUPPORTED, "This file type carries no model data to extract.")
            return
        try:
            info = provider.import_model(storage.resolve_stored(revision.file_path))
            db.execute(delete(BimElement).where(BimElement.revision_id == revision_id))
            seen: set[str] = set()
            skipped, count = 0, 0
            batch: list[BimElement] = []
            for element in provider.list_elements():
                if element.guid in seen:
                    skipped += 1
                    continue
                seen.add(element.guid)
                batch.append(_row(revision_id, element))
                count += 1
                if len(batch) >= BATCH_SIZE:
                    db.add_all(batch)
                    db.flush()
                    batch = []
            db.add_all(batch)
            db.flush()
            note = f"{skipped} duplicate element ids were skipped." if skipped else ""
            _finish(db, revision_id, ExtractionStatus.OK, note, count, info.schema)
        except (BimError, HTTPException) as exc:
            _fail(db, revision_id, exc.detail if isinstance(exc, HTTPException) else str(exc))
        except Exception:  # noqa: BLE001 - background task must record, not raise
            log.exception("Unexpected failure extracting revision %s", revision_id)
            _fail(db, revision_id, "Unexpected error while reading the model. See the server log for details.")


def _fail(db: Session, revision_id: str, message: str) -> None:
    db.rollback()
    db.execute(delete(BimElement).where(BimElement.revision_id == revision_id))
    _finish(db, revision_id, ExtractionStatus.FAILED, message)
