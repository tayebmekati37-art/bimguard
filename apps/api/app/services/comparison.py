from collections import Counter
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.bim.types import ElementData
from app.engines.change_detection import (
    DEFAULT_CONFIG, Change, ChangeDetectionConfig, RevisionMeta, detect_changes, detect_revision_metadata_changes,
)
from app.models.bim import BimElement
from app.models.comparison import DetectedChange, RevisionComparison
from app.models.document import DocumentRevision
from app.models.user import User
from app.services import audit, impact

CHUNK = 500


class ComparisonError(Exception):
    """The comparison cannot be run. The message is safe to show to users."""


def _to_data(row: BimElement) -> ElementData:
    return ElementData(guid=row.guid, ifc_class=row.ifc_class, name=row.name, tag=row.tag, level=row.level,
                       room=row.room, material=row.material, properties=row.properties or {},
                       geometry=row.geometry or {})


def _load(db: Session, revision_id: str, guids: Iterable[str]) -> list[ElementData]:
    wanted = sorted(guids)
    out: list[ElementData] = []
    for i in range(0, len(wanted), CHUNK):
        rows = db.scalars(select(BimElement).where(
            BimElement.revision_id == revision_id, BimElement.guid.in_(wanted[i:i + CHUNK])))
        out += [_to_data(r) for r in rows]
    return out


def _check_ready(old: DocumentRevision, new: DocumentRevision) -> None:
    number = new.document.document_number
    if old.document_id != new.document_id:
        raise ComparisonError("Revisions of different documents cannot be compared.")
    if old.revision_number >= new.revision_number:
        raise ComparisonError(
            f"Revision v{old.revision_number} of {number} is not older than v{new.revision_number}. "
            "Compare an older revision against a newer one.")
    for rev in (old, new):
        prefix = f"Unable to compare revision {number} v{old.revision_number} with v{new.revision_number} because"
        if rev.extraction_status == "pending":
            raise ComparisonError(f"{prefix} revision v{rev.revision_number} is still being processed. "
                                  "Try again in a moment.")
        if rev.extraction_status == "failed":
            raise ComparisonError(f"{prefix} the model data of revision v{rev.revision_number} could not be read "
                                  f"({rev.extraction_message}).")
        if rev.extraction_status != "ok":
            raise ComparisonError(f"{prefix} revision v{rev.revision_number} contains no supported model data.")


def compare_revisions(db: Session, old: DocumentRevision, new: DocumentRevision, user: User | None,
                      config: ChangeDetectionConfig = DEFAULT_CONFIG) -> RevisionComparison:
    _check_ready(old, new)

    # Cheap pre-filter: identical fingerprints are unchanged, so only changed/added/removed rows are loaded.
    old_fp = dict(db.execute(select(BimElement.guid, BimElement.fingerprint)
                             .where(BimElement.revision_id == old.id)).all())
    new_fp = dict(db.execute(select(BimElement.guid, BimElement.fingerprint)
                             .where(BimElement.revision_id == new.id)).all())
    common = old_fp.keys() & new_fp.keys()
    changed = {g for g in common if old_fp[g] != new_fp[g]}
    removed, added = old_fp.keys() - new_fp.keys(), new_fp.keys() - old_fp.keys()

    changes: list[Change] = detect_changes(_load(db, old.id, removed | changed), _load(db, new.id, added | changed),
                                           config)
    changes += detect_revision_metadata_changes(RevisionMeta(old.status.value, old.model_schema),
                                                RevisionMeta(new.status.value, new.model_schema), config)

    db.execute(delete(RevisionComparison).where(RevisionComparison.from_revision_id == old.id,
                                                RevisionComparison.to_revision_id == new.id))
    comparison = RevisionComparison(
        document_id=new.document_id, from_revision_id=old.id, to_revision_id=new.id,
        created_by_id=user.id if user else None, created_by_name=user.full_name if user else "system",
        total_changes=len(changes), config=config.to_dict(),
        counts={"by_type": dict(Counter(c.change_type.value for c in changes)),
                "by_severity": dict(Counter(c.severity.value for c in changes)),
                "elements_old": len(old_fp), "elements_new": len(new_fp),
                "elements_unchanged": len(common) - len(changed)},
    )
    db.add(comparison)
    db.flush()
    db.add_all(DetectedChange(
        comparison_id=comparison.id, element_guid=c.element_guid, element_tag=c.element_tag,
        element_name=c.element_name[:255], ifc_class=c.ifc_class, change_type=c.change_type.value,
        field=c.field[:255], old_value=c.old_value, new_value=c.new_value, severity=c.severity.value,
        confidence=c.confidence, summary=c.summary, match_method=c.match_method, detail=c.detail,
    ) for c in changes)
    audit.record(
        db, user=user, action="revision.compared", entity_type="revision", entity_id=new.id,
        project_id=new.document.project_id,
        detail={"document_number": new.document.document_number, "from": old.revision_number,
                "to": new.revision_number, "changes": len(changes), **comparison.counts["by_severity"]})
    db.commit()
    impact.safe_analyze(db, comparison, user)
    return comparison
