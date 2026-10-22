"""Delete login_attempt rows older than the rate-limit window.

Run periodically from a scheduler. This is not invoked per request;
doing that would add write work to the hot auth path.

    cd apps/api
    python scripts/cleanup_login_attempts.py

Default cutoff is 60 minutes, which is comfortably larger than the
default 15-minute rate-limit window. Safe to run concurrently from
multiple workers.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.rate_limit import cleanup_expired  # noqa: E402


def main() -> int:
    with SessionLocal() as db:
        deleted = cleanup_expired(db, older_than_minutes=60)
    print(f"Deleted {deleted} login attempt(s) older than 60 minutes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())