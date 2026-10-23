# Backup and restore (M20)

## Two backup mechanisms, two purposes

| Mechanism | Endpoint | What it produces | What it is |
| :--- | :--- | :--- | :--- |
| JSON exporter | `POST /admin/backup` | `bimguard-YYYYMMDD-HHMMSS.json` | Portable data export. Row-by-row, human-readable, reloadable with SQLAlchemy. Does not include schema. |
| Native backup | `POST /admin/backup/native` | `bimguard-YYYYMMDD-HHMMSS.db` (SQLite) or `.dump` (Postgres) | Database-native, atomic, restorable. Includes schema implicitly (it is the file). |

Both are valid. The JSON exporter is for moving data between environments or inspecting. The native backup is for recovery after data loss.

## What a native backup includes

Every native backup is three files with the same stem:

    bimguard-YYYYMMDD-HHMMSS.db         the backup itself
    bimguard-YYYYMMDD-HHMMSS.db.meta.json  metadata
    bimguard-YYYYMMDD-HHMMSS.db.sha256  checksum

The metadata contains:

- `schema`: `bimguard.backup.native/1`
- `created_at`: ISO timestamp
- `engine`: `sqlite` or `postgres`
- `database_scheme`, `database_name`, `host`: enough to identify where it came from, without credentials
- `app_version`: from package metadata
- `alembic_revision`: the schema version at backup time
- `file_size_bytes`
- `sha256`: the checksum, duplicated in the sidecar for redundancy
- `tables`: per-table row counts

The checksum sidecar lets an operator run `sha256sum -c` without needing the metadata file.

## SQLite backups

`POST /admin/backup/native` uses Python's stdlib `sqlite3.Connection.backup()`. This is SQLite's online backup API: it copies the database atomically, taking a read lock, and is safe to run while the API holds the file open. No downtime.

The endpoint runs `PRAGMA integrity_check` on the file it just wrote. If the check fails, the file is deleted and the endpoint returns 500. You never get a "backup" that is actually corrupt.

Returns 501 if `DATABASE_URL` is `sqlite://` or `sqlite:///:memory:`: there is no file to copy. Set `DATABASE_URL` to a file path.

## Postgres backups

`POST /admin/backup/native` runs `pg_dump --format=custom`. This requires `pg_dump` to be in the API container's `PATH`. **It is not, by default.** The Dockerfile ships `psycopg` (the Python driver) but not `postgresql-client`.

The endpoint returns 501 with the correct docker command to run from the host:

    docker compose exec -T db pg_dump -U bimguard -F c bimguard > backups/bimguard-$(date +%Y%m%d).dump

That is not a bug; it is a deliberate operational choice. Running `pg_dump` inside the API container would require adding `postgresql-client` to the image, which increases the attack surface of the API container for a task the database container already handles.

If you install `postgresql-client` in the API image, set `PG_DUMP_PATH` to the correct path and the endpoint works. That is a deployment decision, not a code one.

## Restore — SQLite

    powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -BackupPath storage\backups\bimguard-20261022-120000.db -WhatIf
    # review the output
    powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -BackupPath storage\backups\bimguard-20261022-120000.db -Force

The script:

1. Verifies the checksum against the sidecar.
2. Runs `PRAGMA integrity_check` on the backup.
3. Compares the target `DATABASE_URL` against the backup's `engine` field. Refuses if they disagree.
4. Moves the current DB to `<path>.before-restore-<timestamp>` (never deleted).
5. Copies the backup into place.
6. Verifies per-table row counts against the backup's metadata.
7. Exits non-zero if any step fails.

`-WhatIf` shows what would happen without executing. `-Force` is required to actually overwrite.

## Restore — Postgres

The script generates the exact procedure:

    docker compose stop api
    docker compose exec -T db psql -U bimguard -d postgres -c "DROP DATABASE IF EXISTS bimguard;"
    docker compose exec -T db psql -U bimguard -d postgres -c "CREATE DATABASE bimguard;"
    docker compose exec -T db pg_restore -U bimguard -d bimguard -F c < backups/bimguard-20261022.dump
    docker compose start api

It does **not** execute these commands. That is deliberate. Scripting a `DROP DATABASE` against production is how teams lose data during a restore attempt. The operator runs the commands, inspects the output, and verifies row counts against the metadata.

If you are restoring into a fresh database (first install, disaster recovery from scratch), the same procedure applies except step 2 does not need `DROP`.

## Corrupt backup detection

Three independent checks:

1. **Checksum** (`restore.ps1`) — any single byte change is detected.
2. **SQLite integrity** (`PRAGMA integrity_check`) — detects truncation, page corruption, invalid headers.
3. **Postgres dump parseability** (`pg_restore --list`) — checks that the dump format is valid.

A backup that fails any of these is reported as corrupt and the restore aborts before touching the live database.

## Retention

Retention is a **policy**, not a code-enforced action. `BACKUP_RETENTION_DAYS` defaults to 30 and is documented here so operators can configure their own retention automation (cron, lifecycle policies, backup software).

The application **never deletes backups**. A backup system that deletes its own files is one bug away from being a delete system.

## RPO and RTO

These are deployment decisions, not application guarantees.

| Metric | Who sets it | What it means |
| :--- | :--- | :--- |
| **RPO** (recovery point objective) | You | How much data you can afford to lose. If you back up hourly, RPO ≤ 1 hour. |
| **RTO** (recovery time objective) | You | How long restore takes. SQLite restore is minutes. Postgres restore depends on DB size. |

The application provides the tooling (`POST /admin/backup/native`, `scripts/restore.ps1`). It does not and cannot commit to an RPO or RTO. Those come from your backup schedule and your team's practice.

Suggested practice for a first deployment:

- Back up nightly (cron on the host) + on-demand before any migration.
- Retain 30 days.
- Test a restore into a scratch DB once a month. If you have never tested the restore, you do not have a backup.

## What this milestone does NOT provide

- **No scheduled backups.** Scheduling is a deployment decision; use cron, Task Scheduler, or your backup vendor.
- **No automatic retention.** Deleting backups is done by your backup software, not the app.
- **No application-level encryption of backup files.** Use filesystem encryption or your backup vendor's encryption.
- **No cross-region replication.** Backup files live where you put them.
- **No point-in-time recovery (PITR).** That is a Postgres feature (WAL archiving), not an application feature.
- **No automated verification in CI.** The tests verify the backup pipeline works; they do not verify a specific backup is intact. Operators run `restore.ps1 -WhatIf` for that.