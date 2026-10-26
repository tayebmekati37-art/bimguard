# Backup runbook

Operational procedures for BIMGuard backups. This is the "what to do" document.
What is in a backup and how restore works in detail is in `docs/architecture/backup.md`.

## Daily (automatic)

Nightly at 02:00 local time, Windows Task Scheduler runs:

    scripts\backup-now.ps1

This:
1. Detects SQLite or Postgres from DATABASE_URL
2. Runs the backup (SQLite online backup / pg_dump --format=custom)
3. Writes three files: the backup, `.meta.json`, `.sha256`
4. Prunes backups older than `BACKUP_RETENTION_DAYS` (default 30), never touching the newest
5. Copies to `BACKUP_OFF_SITE` if configured
6. Logs everything to `backups\last-run.log`

Install once:

    powershell -ExecutionPolicy Bypass -File scripts\install-backup-schedule.ps1

Uninstall:

    powershell -ExecutionPolicy Bypass -File scripts\install-backup-schedule.ps1 -Uninstall

Linux/macOS equivalent: run `-PrintCron` to see the crontab line.

## Weekly (manual, 1 minute)

Run the health check. This is what you would call from an uptime monitor.

    powershell -ExecutionPolicy Bypass -File scripts\check-backup-health.ps1

Exits 0 if the newest backup is less than 26 hours old and the last log
did not end in FAILED. Exits 1 with a specific message otherwise.

If you have a monitoring system (Healthchecks.io, UptimeRobot, PagerDuty),
wire this script to it. A silent backup failure is the worst failure mode.

## Monthly (manual, 5 minutes)

Run a restore drill. This restores the newest backup into a scratch database
and verifies row counts, then deletes the scratch.

    powershell -ExecutionPolicy Bypass -File scripts\restore-drill.ps1

For SQLite: fully automated.
For Postgres: prints the manual `pg_restore` steps (requires postgresql-client).

**Do not skip this.** A backup you have never restored is not a backup.

## Quarterly (manual, 15 minutes)

Full practice drill, including off-site:

1. Pick the newest off-site backup.
2. Download it to a machine that is not the production host.
3. Run `restore-drill.ps1` against it. If it passes, off-site works.
4. If off-site is not configured, stop reading and configure it. Local backups
   do not survive: disk failure, ransomware, accidental `rm -rf`, or a bad
   `docker compose down -v`.

Set a reminder. A quarterly drill that does not happen is the same as no backup
system, because you will not know whether the backup path still works until
the day you need it.

## On failure

### Backup fails (last-run.log shows FAILED)

1. Read the log: `Get-Content backups\last-run.log -Tail 50`
2. Common causes:
   - **Disk full.** `Get-PSDrive C` — free up space or move backups.
   - **Postgres unreachable.** `docker compose ps` — is `db` up?
   - **`pg_dump` not found.** Postgres backups need `postgresql-client` in the API container. See `docs/architecture/backup.md`.
   - **DATABASE_URL wrong.** Check `apps/api/.env`.
3. Fix the cause, then run `backup-now.ps1` manually to confirm.

### Backup directory is corrupt

If `check-backup-health.ps1` finds a corrupt backup (checksum mismatch), you
have data loss in the backup set, not production. Assess:

1. Are older backups restorable? Run `restore-drill.ps1` after deleting the
   corrupt newest one.
2. Do you have off-site copies from before the corruption? Copy them back.
3. If no backup is restorable: this is the emergency you were preparing for.
   Escalate. Preserve the corrupt files as evidence but do not rely on them.

### You need to actually restore

See `scripts/restore.ps1` (this is the different script from `restore-drill.ps1`).
It restores a backup over the live database after confirming the current one is
preserved.

**Only run this with explicit authorization from whoever owns the data.** A
restore over production loses everything written since the backup was taken.

## Retention policy

Default: 30 days (`BACKUP_RETENTION_DAYS` in `.env`). Backups older than that
are pruned on each successful run.

The pruner **never deletes the newest backup**, even if it is somehow older
than the retention window. If backups have been failing for months, you keep
one stale backup rather than zero.

Adjusting retention:
- **30 days** — small deployments, low write volume. Standard.
- **90 days** — regulated environments, or where investigation into old state is likely.
- **365 days** — financial or legal retention requirements.
- **7 days** — space-constrained, high-frequency backups, aggressive replication elsewhere.

Retention and RPO are related but not the same. Retention is how long you can
go back in time. RPO is how much data you can lose to a failure. See
`docs/architecture/backup.md` for both.

## Off-site configuration

Two supported off-site targets:

**Local or network path (file://):**

    BACKUP_OFF_SITE=file:///D:/backups/bimguard

Simplest. Works if D: is a NAS or an encrypted external drive. Not useful if the
whole machine is stolen or destroyed.

**AWS S3:**

    BACKUP_OFF_SITE=s3://my-bimguard-backups/nightly

Requires `aws` CLI installed and configured (`aws configure`). Uses
`aws s3 cp`. If aws CLI is missing, the off-site copy is skipped (not failed).
Enable S3 server-side encryption with a KMS key — backups contain user data.

If neither is configured, backups are local only. That is documented in
`docs/architecture/encryption.md` as an operator responsibility.

## RPO and RTO

These are decisions, not defaults:

- **RPO** (how much data you can lose): if backups run nightly, worst case is
  one day of data loss. For hourly RPO, change the scheduled task to run hourly.
- **RTO** (how long restore takes): SQLite restore is under a minute for a
  small DB. Postgres restore depends on DB size and pg_restore speed — measure
  on your actual data before you need it.

Neither is a guarantee from the application. Both are determined by your
schedule and your team's practice.

## What this runbook does NOT cover

- **Backup encryption.** See `docs/architecture/encryption.md`. Backups are
  plaintext as written; encryption is the operator's responsibility.
- **Encryption key management.** Also `encryption.md`.
- **Application-level data restoration** (e.g. restoring a single deleted project
  without a full DB restore). Not implemented. A full DB restore is the only
  supported recovery.
- **Point-in-time recovery (PITR).** For Postgres, PITR requires WAL archiving,
  which this application does not configure. Managed Postgres (RDS, Cloud SQL)
  offers it as a provider feature — use that, not BIMGuard scripts.