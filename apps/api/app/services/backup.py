"""Logical data backup.

Dumps every table registered with the ORM to JSON. Works for both SQLite
and Postgres because it uses SQLAlchemy, not a database-specific tool.

What this is: a portable data export that can be inspected and reloaded.
What this is NOT: a schema backup, a point-in-time snapshot, or a
replacement for `pg_dump`. The doc at docs/architecture/deployment.md
explains when to use which.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.db.session import Base

log = logging.getLogger("bimguard.backup")

SCHEMA = "bimguard.backup/1"


def _plain(value):
    """Coerce column values into JSON-safe types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if hasattr(value, "value"):  # enum
        return value.value
    return str(value)


def dump_tables(db: Session) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Return (tables, counts) for every ORM table."""
    tables: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for name, table in Base.metadata.tables.items():
        rows = db.execute(select(table)).mappings().all()
        tables[name] = [{k: _plain(v) for k, v in row.items()} for row in rows]
        counts[name] = len(tables[name])
    return tables, counts


def write_backup(db: Session, directory: Path) -> dict:
    """Dump tables to disk and return metadata about the written file."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    tables, counts = dump_tables(db)

    created = utcnow()
    stamp = created.strftime("%Y%m%d-%H%M%S")
    out_path = directory / f"bimguard-{stamp}.json"

    payload = {
        "schema": SCHEMA,
        "created_at": created.isoformat(),
        "tables": tables,
        "counts": counts,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    size = out_path.stat().st_size
    log.info("Backup written: %s (%d bytes, %d tables)", out_path, size, len(tables))
    return {
        "path": str(out_path),
        "created_at": created.isoformat(),
        "size_bytes": size,
        "tables": counts,
    }