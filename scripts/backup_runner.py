"""Standalone backup runner for scheduled jobs (M26).

Runs without the API. Reads DATABASE_URL from the environment (falls back
to apps/api/.env), calls the existing backup service, prunes old files per
retention policy, optionally copies to off-site storage, and exits 0/1.

Usage:
    apps/api/.venv/Scripts/python.exe scripts/backup_runner.py \
        --output-dir C:\dev\bimguard\backups \
        --retention-days 30

Output: one JSON line on stdout with {status, path, sha256, size_bytes,
engine, pruned: [files], off_site: {mode, status}}.

Exit codes:
    0  backup succeeded
    1  backup failed (database unreachable, disk full, etc.)
    2  backup succeeded but post-processing failed (off-site, prune)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "apps" / "api"
sys.path.insert(0, str(API_DIR))


def _load_env_file(path: Path) -> None:
    """Minimal .env loader. Does not override existing env vars."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _prune(output_dir: Path, retention_days: int, keep_newest: Path) -> list[str]:
    """Delete backup files older than retention_days. Never delete keep_newest.

    A backup "file" here means anything written by the runner: the data file
    (.db or .dump), its .meta.json sidecar, and its .sha256 sidecar. All three
    are pruned together based on the data file's mtime.

    Never deletes the file passed as keep_newest (the one just created), even
    if its mtime is somehow older than the cutoff.
    """
    if retention_days <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    pruned: list[str] = []
    # Group files by stem: any file whose name matches a backup pattern
    patterns = ("bimguard-*.db", "bimguard-*.dump")
    for pattern in patterns:
        for data_file in sorted(output_dir.glob(pattern)):
            if data_file == keep_newest:
                continue
            mtime = datetime.fromtimestamp(data_file.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                continue
            for companion in (
                data_file,
                Path(str(data_file) + ".meta.json"),
                Path(str(data_file) + ".sha256"),
            ):
                if companion.exists():
                    companion.unlink()
                    pruned.append(companion.name)
    return pruned


def _off_site_copy(backup_path: Path, meta_path: Path, checksum_path: Path, target: str) -> dict:
    """Copy the three files to an off-site target.

    Supported schemes:
      file:///abs/path      - copy to that directory
      s3://bucket/prefix    - aws s3 cp (requires aws CLI)
    Anything else: skipped with a logged reason (not a failure).
    """
    if not target:
        return {"mode": "none", "status": "skipped"}

    if target.startswith("file://"):
        # Use url2pathname for correct Windows handling:
        #   file:///C:/Users/... -> C:\Users\...
        #   file:///mnt/backups -> /mnt/backups
        # The previous logic (target[len("file://"):]) produced "/C:/Users/..."
        # on Windows, which Path() treats as a relative-to-drive-root path,
        # not the absolute path the user meant.
        from urllib.parse import urlparse
        from urllib.request import url2pathname
        parsed = urlparse(target)
        dest_dir = Path(url2pathname(parsed.path))
        if not dest_dir.exists():
            return {"mode": "file", "status": "failed", "reason": f"target dir does not exist: {dest_dir}"}
        try:
            for src in (backup_path, meta_path, checksum_path):
                if src.exists():
                    shutil.copy2(src, dest_dir / src.name)
            return {"mode": "file", "status": "ok", "dest": str(dest_dir)}
        except OSError as e:
            return {"mode": "file", "status": "failed", "reason": str(e)}

    if target.startswith("s3://"):
        aws = shutil.which("aws")
        if not aws:
            return {"mode": "s3", "status": "skipped", "reason": "aws CLI not in PATH"}
        try:
            for src in (backup_path, meta_path, checksum_path):
                if src.exists():
                    subprocess.run(
                        [aws, "s3", "cp", str(src), target.rstrip("/") + "/" + src.name],
                        check=True, capture_output=True, timeout=300,
                    )
            return {"mode": "s3", "status": "ok", "dest": target}
        except subprocess.CalledProcessError as e:
            return {"mode": "s3", "status": "failed", "reason": (e.stderr or b"").decode("utf-8", "replace")[:500]}
        except subprocess.TimeoutExpired:
            return {"mode": "s3", "status": "failed", "reason": "aws s3 cp timed out"}

    return {"mode": "unknown", "status": "skipped", "reason": f"unsupported scheme: {target}"}


def run_backup(
    output_dir: Path,
    retention_days: int = 30,
    off_site: str = "",
) -> dict:
    """Run one backup. Returns a dict describing the result.

    The exit-code contract is decided by the caller from this dict:
      status == "ok"                          -> 0
      status == "ok" but off_site failed      -> 2
      status == "failed"                      -> 1
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SaSession
    from app.services import backup as backup_service

    output_dir.mkdir(parents=True, exist_ok=True)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return {"status": "failed", "reason": "DATABASE_URL is not set"}

    # Open our own engine from the current DATABASE_URL. This is required
    # because:
    #   1. The runner is a standalone script (called by backup-now.ps1 via
    #      subprocess) and must not depend on cached app state.
    #   2. app.db.session.SessionLocal is created at import time from
    #      get_settings() and is lru_cached; if DATABASE_URL changes after
    #      that (tests monkeypatch it; a long-running process might reload
    #      config), SessionLocal still points at the old database.
    try:
        engine = create_engine(db_url)
        try:
            with SaSession(engine) as db:
                result = backup_service.native_backup(db, output_dir, db_url=db_url)
        finally:
            engine.dispose()
    except Exception as e:
        return {"status": "failed", "reason": f"{type(e).__name__}: {e}"}

    data_path = Path(result.path)
    meta_path = Path(result.meta_path)
    checksum_path = Path(result.checksum_path)

    pruned = _prune(output_dir, retention_days, keep_newest=data_path)

    off_site_result = _off_site_copy(data_path, meta_path, checksum_path, off_site)
    exit_ok = off_site_result["status"] in ("ok", "skipped")

    return {
        "status": "ok" if exit_ok else "partial",
        "path": str(data_path),
        "size_bytes": result.size_bytes,
        "sha256": result.sha256,
        "engine": result.engine,
        "alembic_revision": result.alembic_revision,
        "pruned": pruned,
        "off_site": off_site_result,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--retention-days", type=int, default=30)
    ap.add_argument("--off-site", default="", help="file:///abs/path or s3://bucket/prefix")
    args = ap.parse_args()

    _load_env_file(API_DIR / ".env")

    try:
        result = run_backup(
            output_dir=Path(args.output_dir),
            retention_days=args.retention_days,
            off_site=args.off_site,
        )
    except Exception as e:
        result = {"status": "failed", "reason": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if result["status"] == "failed":
        return 1
    if result["status"] == "partial":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())