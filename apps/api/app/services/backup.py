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

# =====================================================================
# Native backup (M20)
# =====================================================================
# The JSON exporter above is a portable data export. It is not a backup:
# no schema, no tested restore, no integrity metadata. This section adds
# a real backup path.
#
# SQLite: uses the stdlib sqlite3 online backup API. Atomic, consistent,
# safe to run while the API holds the file open.
#
# Postgres: shells out to pg_dump in custom format. Returns 501 from the
# endpoint when pg_dump is not present, which is the correct behaviour for
# an API container that ships psycopg but not postgresql-client. Production
# Postgres backups use `docker compose exec db pg_dump`, documented in
# docs/architecture/backup.md.

import hashlib
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass

from sqlalchemy.engine import make_url

from app.core.config import get_settings


class BackupError(Exception):
    """A backup could not be produced or verified."""


class BackupUnavailableError(BackupError):
    """Backup is not supported for this configuration."""


@dataclass
class NativeBackupResult:
    path: str
    meta_path: str
    checksum_path: str
    sha256: str
    size_bytes: int
    engine: str
    alembic_revision: str | None
    tables: dict[str, int]


def _app_version() -> str:
    try:
        import importlib.metadata as md
        return md.version("bimguard-api")
    except Exception:  # noqa: BLE001
        return "0.0.0+unknown"


def _alembic_revision(db: Session) -> str | None:
    from sqlalchemy import text
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001
        return None


def _sqlite_file_from_url(db_url: str) -> Path | None:
    """Return the on-disk path for a SQLite URL, or None for in-memory."""
    url = make_url(db_url)
    if url.get_backend_name() != "sqlite":
        return None
    database = url.database
    if not database or database == ":memory:":
        return None
    return Path(database)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_backup(db: Session, out_dir: Path, db_url: str) -> NativeBackupResult:
    src_path = _sqlite_file_from_url(db_url)
    if src_path is None:
        raise BackupUnavailableError(
            "In-memory SQLite has no file to back up. Set DATABASE_URL to a "
            "file-based path (e.g. sqlite:///./bimguard_dev.db)."
        )
    if not src_path.exists():
        raise BackupError(f"SQLite database file not found: {src_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    created = utcnow()
    stamp = created.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"bimguard-{stamp}.db"

    try:
        src = sqlite3.connect(str(src_path))
        try:
            dst = sqlite3.connect(str(out_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite backup failed: {exc}") from exc

    # Integrity check on the file we just wrote.
    try:
        check = sqlite3.connect(str(out_path))
        try:
            status = check.execute("PRAGMA integrity_check").fetchone()
        finally:
            check.close()
    except sqlite3.Error as exc:
        out_path.unlink(missing_ok=True)
        raise BackupError(f"Backup failed integrity check: {exc}") from exc
    if not status or status[0] != "ok":
        out_path.unlink(missing_ok=True)
        raise BackupError(f"Backup integrity check returned: {status!r}")

    _, counts = dump_tables(db)
    sha = _sha256_file(out_path)
    revision = _alembic_revision(db)

    return _write_sidecars(
        out_path=out_path, db_url=db_url, engine="sqlite",
        sha=sha, tables=counts, revision=revision,
        created=created,
    )


def _postgres_backup(db: Session, out_dir: Path, db_url: str) -> NativeBackupResult:
    s = get_settings()
    if shutil.which(s.pg_dump_path) is None:
        raise BackupUnavailableError(
            "pg_dump is not available in this container. "
            "For Postgres, run from the host: "
            "docker compose exec -T db pg_dump -U bimguard -F c bimguard > backup.dump"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    created = utcnow()
    stamp = created.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"bimguard-{stamp}.dump"

    try:
        subprocess.run(
            [s.pg_dump_path, "--format=custom", "--file", str(out_path), db_url],
            check=True, capture_output=True, timeout=300,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        out_path.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {exc}") from exc

    # Verify the dump is parseable.
    try:
        subprocess.run(
            [s.pg_dump_path.replace("pg_dump", "pg_restore"), "--list", str(out_path)],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BackupError(f"pg_restore --list rejected the dump: {exc}") from exc

    _, counts = dump_tables(db)
    sha = _sha256_file(out_path)
    revision = _alembic_revision(db)

    return _write_sidecars(
        out_path=out_path, db_url=db_url, engine="postgres",
        sha=sha, tables=counts, revision=revision,
        created=created,
    )


def _write_sidecars(
    *, out_path: Path, db_url: str, engine: str,
    sha: str, tables: dict[str, int], revision: str | None,
    created,
) -> NativeBackupResult:
    url = make_url(db_url)
    meta = {
        "schema": "bimguard.backup.native/1",
        "created_at": created.isoformat(),
        "engine": engine,
        "database_scheme": url.get_backend_name(),
        "database_name": url.database,
        "host": url.host,
        "app_version": _app_version(),
        "alembic_revision": revision,
        "file_size_bytes": out_path.stat().st_size,
        "sha256": sha,
        "tables": tables,
    }
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    checksum_path = out_path.with_suffix(out_path.suffix + ".sha256")
    checksum_path.write_text(f"{sha}  {out_path.name}\n", encoding="utf-8")

    log.info("Native backup written: %s (%d bytes, sha256=%s…)", out_path, meta["file_size_bytes"], sha[:12])
    return NativeBackupResult(
        path=str(out_path),
        meta_path=str(meta_path),
        checksum_path=str(checksum_path),
        sha256=sha,
        size_bytes=meta["file_size_bytes"],
        engine=engine,
        alembic_revision=revision,
        tables=tables,
    )


def native_backup(db: Session, out_dir: Path, db_url: str | None = None) -> NativeBackupResult:
    """Produce a native database backup with metadata and checksum sidecars."""
    db_url = db_url or get_settings().database_url
    scheme = make_url(db_url).get_backend_name()
    if scheme == "sqlite":
        return _sqlite_backup(db, Path(out_dir), db_url)
    if scheme in ("postgres", "postgresql"):
        return _postgres_backup(db, Path(out_dir), db_url)
    raise BackupUnavailableError(f"Native backup not implemented for engine '{scheme}'.")