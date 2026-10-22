"""Delete revoked-token rows whose expiry has passed."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.revoked_token import RevokedToken  # noqa: E402


def main() -> int:
    # Use the database's own now() so we do not mix naive and aware
    # datetimes. SQLite drops tzinfo on DateTime(timezone=True) columns,
    # so a Python-side aware datetime would compare incorrectly.
    with SessionLocal() as db:
        result = db.execute(
            delete(RevokedToken).where(RevokedToken.expires_at < func.now())
        )
        db.commit()
        deleted = result.rowcount or 0
    print(f"Deleted {deleted} revoked token(s) with expires_at < now()")
    return 0


if __name__ == "__main__":
    sys.exit(main())