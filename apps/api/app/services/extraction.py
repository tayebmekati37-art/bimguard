import logging
import threading
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.bim.provider import BIMProvider, BimError, BimUnavailableError
from app.bim.registry import provider_for
from app.bim.types import ElementData, ModelInfo
from app.models.bim import BimElement
from app.models.document import DocumentRevision, ExtractionStatus
from app.services import audit, comparison, storage

log = logging.getLogger("bimguard.extraction")
BATCH_SIZE = 1000
PARSE_ATTEMPTS = 3

# IfcOpenShell is not safe to run from several threads at once, and uploads schedule one background task each.
# Models are therefore parsed one at a time per server process.
_PARSE_LOCK = threading.Lock()


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
        db, user=None,
        action="revision.extracted" if status == ExtractionStatus.OK else f"revision.extraction_{status.value}",
        entity_type="revision", entity_id=revision.id, project_id=revision.document.project_id,
        detail={"document_number": revision.document.document_number, "revision": revision.revision_number,
                "elements": count, "message": message},
    )
    db.commit()


def _import_with_retry(provider: BIMProvider, path: Path) -> ModelInfo:
    """A file that was written moments ago can be briefly locked (for example by antivirus scanning),
    which surfaces as a parse error. Retry a couple of times before reporting failure."""
    for attempt in range(PARSE_ATTEMPTS):
        try:
            return provider.import_model(path)
        except BimUnavailableError:
            raise
        except BimError as exc:
            if attempt < PARSE_ATTEMPTS - 1 and "could not be parsed" in str(exc):
                log.warning("Parse attempt %s failed (%s); retrying", attempt + 1, exc)
                time.sleep(1.0 * (attempt + 1))
                continue
            raise
    raise AssertionError("unreachable")


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
        succeeded = False
        try:
            with _PARSE_LOCK:
                info = _import_with_retry(provider, storage.resolve_stored(revision.file_path))
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
            succeeded = True
        except (BimError, HTTPException) as exc:
            _fail(db, revision_id, exc.detail if isinstance(exc, HTTPException) else str(exc))
        except Exception as exc:  # noqa: BLE001 - background task must record, not raise
            log.exception("Unexpected failure extracting revision %s", revision_id)
            _fail(db, revision_id, f"Unexpected error while reading the model ({type(exc).__name__}). "
                                   "See the server log for details.")
        if succeeded:
            _auto_compare(db, revision_id)


def _auto_compare(db: Session, revision_id: str) -> None:
    """Compares a freshly extracted revision with its predecessor, and its successor with it (extractions can
    finish out of order). Failures never affect extraction."""
    revision = db.get(DocumentRevision, revision_id)
    if revision is None:
        return
    pairs: list[tuple[DocumentRevision, DocumentRevision]] = []
    if revision.previous_revision_id:
        previous = db.get(DocumentRevision, revision.previous_revision_id)
        if previous is not None and previous.extraction_status == ExtractionStatus.OK.value:
            pairs.append((previous, revision))
    successor = db.scalar(select(DocumentRevision).where(DocumentRevision.previous_revision_id == revision_id))
    if successor is not None and successor.extraction_status == ExtractionStatus.OK.value:
        pairs.append((revision, successor))
    for old, new in pairs:
        try:
            comparison.compare_revisions(db, old, new, user=None)
        except comparison.ComparisonError as exc:
            log.info("Automatic comparison skipped: %s", exc)
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("Automatic comparison failed for revision %s", new.id)


def _fail(db: Session, revision_id: str, message: str) -> None:
    db.rollback()
    db.execute(delete(BimElement).where(BimElement.revision_id == revision_id))
    _finish(db, revision_id, ExtractionStatus.FAILED, message)


def requeue_pending(session_factory: sessionmaker) -> int:
    """Re-runs extraction for revisions left 'pending', for example by a server restart. Oldest first, so
    each revision's predecessor is ready when it is compared."""
    with session_factory() as db:
        ids = list(db.scalars(select(DocumentRevision.id)
                              .where(DocumentRevision.extraction_status == ExtractionStatus.PENDING.value)
                              .order_by(DocumentRevision.uploaded_at, DocumentRevision.revision_number)))
    for revision_id in ids:
        extract_revision(session_factory, revision_id)
    return len(ids)
