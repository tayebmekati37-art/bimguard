from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import Role, User
from app.services import audit
from app.services import backup as backup_service
from app.services.backup import BackupError, BackupUnavailableError

router = APIRouter(tags=["admin"])
admin_only = require_roles(Role.ADMIN)


@router.post("/admin/backup")
def create_backup(db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    """Write a JSON logical backup of every ORM table to storage/backups/.

    Returns the path, size, and per-table row counts from the file that
    was just written. Idempotent in spirit: each call writes a new
    timestamped file.
    """
    settings = get_settings()
    backup_dir = Path(settings.storage_dir) / "backups"
    result = backup_service.write_backup(db, backup_dir)
    audit.record(
        db, user=user, action="admin.backup", entity_type="system",
        entity_id=None, detail={"path": result["path"], "size_bytes": result["size_bytes"]},
    )
    db.commit()
    return result

@router.post("/admin/backup/native")
def create_native_backup(db: Session = Depends(get_db), user: User = Depends(admin_only)) -> dict:
    """Native database backup with metadata and checksum sidecars.

    SQLite: uses sqlite3 online backup; atomic, safe while the API is running.
    Postgres: returns 501 unless pg_dump is available; see the error message
    for the exact docker command to run from the host.
    """
    settings = get_settings()
    backup_dir = Path(settings.backup_dir) if settings.backup_dir else Path(settings.storage_dir) / "backups"
    try:
        result = backup_service.native_backup(db, backup_dir)
    except BackupUnavailableError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    except BackupError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc

    audit.record(
        db, user=user, action="admin.backup.native", entity_type="system",
        entity_id=None,
        detail={
            "path": result.path,
            "size_bytes": result.size_bytes,
            "engine": result.engine,
            "sha256": result.sha256,
        },
    )
    db.commit()
    return {
        "path": result.path,
        "meta_path": result.meta_path,
        "checksum_path": result.checksum_path,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "engine": result.engine,
        "alembic_revision": result.alembic_revision,
        "tables": result.tables,
    }
