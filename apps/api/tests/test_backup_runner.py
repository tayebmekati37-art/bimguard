"""Tests for scripts/backup_runner.py (M26)."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from app.core.security import hash_password
from app.db.session import Base
from app.models.user import Role, User


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    """A real SQLite DB at a temp path, DATABASE_URL set, one user seeded."""
    db_path = tmp_path / "src.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)

    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "  version_num VARCHAR(32) NOT NULL,"
            "  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
            ")"
        ))
        conn.execute(text("INSERT OR REPLACE INTO alembic_version (version_num) VALUES ('test')"))
    with Session(engine) as db:
        db.add(User(email="a@test.local", full_name="A", role=Role.ADMIN,
                    password_hash=hash_password("x")))
        db.commit()
    engine.dispose()
    yield url, db_path


def test_run_backup_creates_files(sqlite_db, tmp_path):
    from backup_runner import run_backup
    out = tmp_path / "backups"
    result = run_backup(out, retention_days=30, off_site="")
    assert result["status"] == "ok", result
    assert Path(result["path"]).exists()
    assert Path(result["path"] + ".meta.json").exists()
    assert Path(result["path"] + ".sha256").exists()
    assert result["size_bytes"] > 0
    assert result["engine"] == "sqlite"


def test_run_backup_has_valid_sqlite(sqlite_db, tmp_path):
    from backup_runner import run_backup
    out = tmp_path / "backups"
    result = run_backup(out, retention_days=30, off_site="")
    conn = sqlite3.connect(result["path"])
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    finally:
        conn.close()


def test_run_backup_metadata_has_sha256(sqlite_db, tmp_path):
    from backup_runner import run_backup
    out = tmp_path / "backups"
    result = run_backup(out, retention_days=30, off_site="")
    meta = json.loads(Path(result["path"] + ".meta.json").read_text(encoding="utf-8"))
    assert meta["sha256"] == result["sha256"]
    assert meta["engine"] == "sqlite"
    assert meta["tables"]["users"] == 1


def test_run_backup_fails_without_database_url(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backup_runner import run_backup
    result = run_backup(tmp_path / "backups", retention_days=30, off_site="")
    assert result["status"] == "failed"
    assert "DATABASE_URL" in result["reason"]


def test_prune_removes_old_backups(sqlite_db, tmp_path):
    from backup_runner import run_backup, _prune
    out = tmp_path / "backups"
    out.mkdir()
    # Create a fake old backup trio
    old = out / "bimguard-20200101-000000.db"
    old.write_bytes(b"fake")
    Path(str(old) + ".meta.json").write_text("{}")
    Path(str(old) + ".sha256").write_text("x")
    past = datetime.now(timezone.utc) - timedelta(days=90)
    import os
    ts = past.timestamp()
    os.utime(old, (ts, ts))

    # Create a new backup so keep_newest is a real file
    result = run_backup(out, retention_days=30, off_site="")
    assert result["status"] == "ok"
    assert any("20200101" in p for p in result["pruned"])
    assert not old.exists()


def test_prune_keeps_most_recent_even_if_old(sqlite_db, tmp_path, monkeypatch):
    """If all backups are old (because backups have been failing), do not delete
    the only one. Better to keep a stale backup than none."""
    from backup_runner import _prune
    out = tmp_path / "backups"
    out.mkdir()
    only = out / "bimguard-20200101-000000.db"
    only.write_bytes(b"x")
    past = datetime.now(timezone.utc) - timedelta(days=999)
    import os
    ts = past.timestamp()
    os.utime(only, (ts, ts))
    # keep_newest passed as the only file, so it must survive
    pruned = _prune(out, retention_days=30, keep_newest=only)
    assert only.exists()
    assert pruned == []


def test_off_site_file_copy(sqlite_db, tmp_path):
    from backup_runner import run_backup
    out = tmp_path / "backups"
    remote = tmp_path / "remote"
    remote.mkdir()
    result = run_backup(out, retention_days=30, off_site=f"file:///{remote.as_posix().lstrip('/')}")
    assert result["status"] == "ok"
    # The backup file name should exist under remote
    name = Path(result["path"]).name
    assert (remote / name).exists()


def test_off_site_missing_target_is_partial(sqlite_db, tmp_path):
    from backup_runner import run_backup
    out = tmp_path / "backups"
    # Target dir that does not exist
    target = f"file:///{(tmp_path / 'does-not-exist').as_posix().lstrip('/')}"
    result = run_backup(out, retention_days=30, off_site=target)
    # backup itself succeeded, off-site failed -> partial
    assert result["status"] == "partial"
    assert Path(result["path"]).exists()
    assert result["off_site"]["status"] == "failed"


def test_off_site_unknown_scheme_is_skipped_not_failed(sqlite_db, tmp_path):
    from backup_runner import run_backup
    result = run_backup(tmp_path / "backups", retention_days=30, off_site="ftp://nope")
    assert result["status"] == "ok"  # skipping is not a failure
    assert result["off_site"]["status"] == "skipped"