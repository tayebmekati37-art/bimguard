from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import Role, User
from app.services import audit
from app.services import backup as backup_service

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