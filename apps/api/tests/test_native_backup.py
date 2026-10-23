"""Tests for M20 native backup and restore."""
import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import Base
from app.models.user import Role, User
from app.services.backup import (
    BackupError,
    BackupUnavailableError,
    _sha256_file,
    _sqlite_file_from_url,
    native_backup,
)


@pytest.fixture
def file_sqlite(tmp_path):
    """A real file-based SQLite DB with a couple of rows and an alembic_version.

    Base.metadata.create_all() only creates ORM tables, not alembic_version,
    so we create it explicitly. A production DB always has it after
    `alembic upgrade head`; the restore test needs it to verify the schema
    version survives the backup.
    """
    db_path = tmp_path / "src.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "  version_num VARCHAR(32) NOT NULL,"
            "  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
            ")"
        ))
        conn.execute(text(
            "INSERT OR REPLACE INTO alembic_version (version_num) VALUES ('test_rev')"
        ))

    with Session(engine) as db:
        db.add(User(
            email="admin@test.local", full_name="Admin",
            role=Role.ADMIN, password_hash=hash_password("x"),
        ))
        db.add(User(
            email="eng@test.local", full_name="Eng",
            role=Role.ENGINEER, password_hash=hash_password("x"),
        ))
        db.commit()

    yield f"sqlite:///{db_path}", db_path, engine
    engine.dispose()


# ------------------------------------------------------------------ url parsing

def test_sqlite_file_from_url_extracts_path(tmp_path):
    p = tmp_path / "x.db"
    assert _sqlite_file_from_url(f"sqlite:///{p}") == Path(str(p))


def test_sqlite_file_from_url_returns_none_for_memory():
    assert _sqlite_file_from_url("sqlite://") is None
    assert _sqlite_file_from_url("sqlite:///:memory:") is None


# ------------------------------------------------------------------ native_backup happy path

def test_native_backup_sqlite_produces_valid_file(file_sqlite, tmp_path):
    url, src_path, engine = file_sqlite
    out_dir = tmp_path / "backups"

    with Session(engine) as db:
        result = native_backup(db, out_dir, db_url=url)

    backup_path = Path(result.path)
    assert backup_path.exists()
    assert backup_path.suffix == ".db"
    assert result.engine == "sqlite"
    assert result.size_bytes > 0

    # Opens cleanly, integrity ok
    conn = sqlite3.connect(str(backup_path))
    try:
        status = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert status == "ok"
        count = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_native_backup_writes_metadata_and_checksum(file_sqlite, tmp_path):
    url, _, engine = file_sqlite
    out_dir = tmp_path / "backups"
    with Session(engine) as db:
        result = native_backup(db, out_dir, db_url=url)

    meta = json.loads(Path(result.meta_path).read_text(encoding="utf-8"))
    assert meta["schema"] == "bimguard.backup.native/1"
    assert meta["engine"] == "sqlite"
    assert meta["sha256"] == result.sha256
    assert meta["tables"]["users"] == 2
    assert meta["file_size_bytes"] == result.size_bytes

    checksum_text = Path(result.checksum_path).read_text(encoding="utf-8")
    assert result.sha256 in checksum_text
    assert Path(result.path).name in checksum_text


def test_native_backup_sha256_matches_file(file_sqlite, tmp_path):
    url, _, engine = file_sqlite
    with Session(engine) as db:
        result = native_backup(db, tmp_path / "backups", db_url=url)

    on_disk = _sha256_file(Path(result.path))
    assert on_disk == result.sha256


def test_native_backup_metadata_records_row_counts(file_sqlite, tmp_path):
    url, _, engine = file_sqlite
    with Session(engine) as db:
        result = native_backup(db, tmp_path / "backups", db_url=url)

    # Two users inserted by the fixture
    assert result.tables["users"] == 2


# ------------------------------------------------------------------ failure modes

def test_native_backup_in_memory_sqlite_raises(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(BackupUnavailableError, match="In-memory SQLite"):
            native_backup(db, tmp_path / "backups", db_url="sqlite://")


def test_native_backup_postgres_without_pg_dump_raises(tmp_path, monkeypatch):
    # Simulate pg_dump not being in PATH
    monkeypatch.setattr("shutil.which", lambda _: None)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(BackupUnavailableError, match="pg_dump"):
            native_backup(
                db, tmp_path / "backups",
                db_url="postgresql+psycopg://u:p@localhost/db",
            )


# ------------------------------------------------------------------ restore

def test_restore_reproduces_row_counts(file_sqlite, tmp_path):
    """The whole point of M20: a restored DB has the same rows as the source."""
    url, _, engine = file_sqlite

    with Session(engine) as db:
        result = native_backup(db, tmp_path / "backups", db_url=url)

    # Restore = copy the backup to a new path and open it. This mirrors
    # what scripts/restore.ps1 does for SQLite.
    restored_path = tmp_path / "restored.db"
    restored_path.write_bytes(Path(result.path).read_bytes())

    restored_engine = create_engine(f"sqlite:///{restored_path}")
    try:
        with restored_engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM users")).scalar()
            assert count == result.tables["users"]

            # Alembic version is preserved (table exists, row copied)
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == result.alembic_revision
    finally:
        restored_engine.dispose()


def test_corrupt_backup_fails_integrity_check(file_sqlite, tmp_path):
    """Truncated backup files must be detectable.

    A truncated SQLite file can fail two ways:
      - PRAGMA integrity_check returns a string != 'ok'
      - sqlite3 raises DatabaseError immediately on execute

    Both are valid "this is corrupt" signals. The important thing is that
    the corrupt file is NEVER treated as ok.
    """
    url, _, engine = file_sqlite
    with Session(engine) as db:
        result = native_backup(db, tmp_path / "backups", db_url=url)

    backup_path = Path(result.path)
    # Truncate to 100 bytes — enough to lose the header or critical pages
    backup_path.write_bytes(backup_path.read_bytes()[:100])

    detected_as_corrupt = False
    detail = ""
    try:
        conn = sqlite3.connect(str(backup_path))
        try:
            status = conn.execute("PRAGMA integrity_check").fetchone()
            detail = repr(status)
            if not status or status[0] != "ok":
                detected_as_corrupt = True
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        detected_as_corrupt = True
        detail = f"DatabaseError: {exc}"

    assert detected_as_corrupt, (
        f"truncated SQLite backup was not detected as corrupt. Detail: {detail}"
    )


def test_checksum_mismatch_is_detectable(file_sqlite, tmp_path):
    """A modified backup must not match its recorded checksum."""
    url, _, engine = file_sqlite
    with Session(engine) as db:
        result = native_backup(db, tmp_path / "backups", db_url=url)

    backup_path = Path(result.path)
    original = backup_path.read_bytes()
    # Append a byte; the file is still openable by sqlite but the checksum changes
    backup_path.write_bytes(original + b"\x00")
    assert _sha256_file(backup_path) != result.sha256


# ------------------------------------------------------------------ endpoint

def test_native_backup_endpoint_requires_admin(client, auth):
    r = client.post("/admin/backup/native", headers=auth("engineer"))
    assert r.status_code == 403
    r = client.post("/admin/backup/native", headers=auth("bim_coordinator"))
    assert r.status_code == 403


def test_native_backup_endpoint_requires_auth(client):
    r = client.post("/admin/backup/native")
    assert r.status_code == 401


def test_native_backup_endpoint_against_in_memory_returns_501(client, auth):
    """The test DB is sqlite:// (in-memory); endpoint must say so clearly."""
    r = client.post("/admin/backup/native", headers=auth("admin"))
    assert r.status_code == 501
    assert "In-memory SQLite" in r.json()["detail"]


# ------------------------------------------------------------------ regression

def test_json_backup_still_works(client, auth, monkeypatch, tmp_path):
    """M17's JSON exporter must keep working alongside the native path."""
    from app.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "storage_dir", str(tmp_path))
    r = client.post("/admin/backup", headers=auth("admin"))
    assert r.status_code == 200
    assert Path(r.json()["path"]).exists()