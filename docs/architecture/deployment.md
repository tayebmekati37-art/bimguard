# Deployment and trust

> Backup and restore are covered in docs/architecture/backup.md (M20). This document covers the deployment environment, secret handling, and the remaining scope boundaries.

## What this milestone ships

### 1. Role capability map at `GET /me/permissions`

Returns `{role, capabilities: {name: bool}}` for the current user. The
single source of truth is `app/services/permissions.py`; every
`require_roles(...)` guard in `app/api/` is mirrored there. The frontend
can use it to hide controls the backend would reject.

### 2. JWT secret safety

`app/core/security.py:ensure_secret_is_safe()` runs once at startup.
- If `environment` is `production`, `prod`, or `staging` and `JWT_SECRET`
  is still one of the known defaults, startup raises `RuntimeError`.
- Otherwise it logs a single warning.

This makes "did you change the secret before deploying?" a hard gate
instead of a checklist item.

### 3. `POST /admin/backup` (admin-only)

Writes a JSON dump of every ORM table to `storage/backups/bimguard-<timestamp>.json`.
Works for both SQLite and Postgres because it uses SQLAlchemy, not a
database-specific tool.

Response: `{path, created_at, size_bytes, tables: {name: count}}`.

The file contains:

    {
      "schema": "bimguard.backup/1",
      "created_at": "ISO-8601",
      "tables": { "users": [...], "projects": [...], ... },
      "counts": { "users": 5, "projects": 3, ... }
    }

### 4. RBAC audit test

`tests/test_rbac_audit.py` walks every `APIRoute` in `app.routes` and
asserts `get_current_user` appears somewhere in the dependency tree,
except for two intentionally public routes (`POST /auth/login`,
`GET /health`). Adding an unprotected endpoint in a future milestone
fails this test.

### 5. Audit immutability test

`tests/test_audit_immutability.py` greps the source tree:
- `AuditLog(...)` must only be constructed inside `services/audit.py`.
- Nothing may `delete` or `update` `AuditLog` outside that module.

This turns "audit rows are write-once" from a claim into an invariant
enforced on every test run.

### 6. Container health check

The `api` service in `docker-compose.yml` now has a `healthcheck:` that
calls `/health` using Python (no `curl` dependency in the image). If the
API fails to start or hangs, Docker restarts or reports it as unhealthy.

### 7. Security behaviour tests

`tests/test_auth_security.py` covers:
- Expired token → 401
- Forged signature → 401
- No token → 401
- Viewer cannot POST /projects → 403
- Viewer cannot POST /projects/{id}/validate → 403
- Viewer cannot acknowledge issues → 403
- Engineer cannot DELETE /projects/{id} → 403
- Engineer cannot activate a profile → 403
- Engineer cannot read /audit-logs → 403
- Engineer cannot POST /admin/backup → 403

## Backup and restore

### Backup

    curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/backup

The response includes the path to the file. Copy it off-machine as you
would any backup.

### Restore (SQLite)

This procedure assumes a clean database and the same schema.

1. Stop the API.
2. Drop or move the current database file aside.
3. Recreate the schema:
       cd apps/api
       .\.venv\Scripts\alembic.exe upgrade head
4. Load the backup JSON into the empty schema. There is no first-class
   restore endpoint yet; use a short Python script:

       import json
       from app.db.session import SessionLocal, Base
       from sqlalchemy import insert

       payload = json.load(open("bimguard-YYYYMMDD-HHMMSS.json", encoding="utf-8"))
       with SessionLocal() as db:
           for name in ["users", "projects", "documents", "document_revisions",
                        "dependencies", "validation_runs", "validation_issues",
                        "audit_logs", "notifications"]:
               rows = payload["tables"].get(name, [])
               if not rows:
                   continue
               db.execute(insert(Base.metadata.tables[name]), rows)
           db.commit()

   Order matters: load parent tables (users, projects) before children.
5. Start the API.

**This restore is not a database snapshot restore.** It does not restore
sequences, indexes, or PostgreSQL types. It restores data rows into a
schema created by Alembic.

### Restore (Postgres)

For point-in-time Postgres backups, use `pg_dump` on the `db` service.
This is the standard and it is not replaced by `POST /admin/backup`:

    docker compose exec db pg_dump -U bimguard bimguard > bimguard.sql
    # later:
    docker compose exec -T db psql -U bimguard bimguard < bimguard.sql

`POST /admin/backup` is a *logical data export* usable across database
engines. `pg_dump` is a *physical/logical snapshot* specific to Postgres.
Use both: JSON for portability and inspection, `pg_dump` for operational
recovery.

## Environment variables

| Variable | Purpose | Default | Production |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./bimguard_dev.db` | Postgres URL |
| `JWT_SECRET` | Signing key for access tokens | dev default | **must** be set |
| `JWT_ALGORITHM` | Signing algorithm | `HS256` | `HS256` |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `60` | ≤ 60 |
| `ENVIRONMENT` | `development` / `staging` / `production` | `development` | `production` |
| `STORAGE_DIR` | Uploaded file storage | `./storage` | Persistent volume |
| `MAX_UPLOAD_MB` | Upload size limit | `50` | As needed |
| `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY` | Optional AI provider | unset | Optional |

`.env` must never be committed. `.env.example` lists every variable with
placeholder values.

## What this milestone does NOT ship

### Token revocation

Access tokens are valid until they expire. Logging out on the frontend
only clears the local copy. There is no server-side revocation list.
**Consequence:** a stolen token remains valid until its `exp`.

**Adding it later:** a `jti` claim on tokens plus a `revoked_tokens` table,
checked in `get_current_user`. Out of scope for M17.

### Encryption at rest

The SQLite file and Postgres volume are unencrypted on disk. Anyone with
filesystem access can read them.

**Adding it later:** SQLCipher (SQLite) or disk-level encryption (Postgres
via LUKS or a managed service). Out of scope for M17.

### Multi-tenant isolation

This is a **single-tenant system**: every authenticated user can read
every project. Roles control writes, not reads. "Project-level
authorization" in the strict sense (user A cannot see user B's project)
does not apply because there is no concept of project ownership beyond
`created_by_id`, which is informational.

**Adding it later:** `ProjectMember` table with role-per-project,
`require_project_member(...)` dependency added to every project-scoped
route, migration, and updates to every test. Substantial; out of scope
for M17.

### Login rate limiting

There is no limit on `POST /auth/login` attempts. Brute-force protection
is not implemented.

**Adding it later:** slowapi or a middleware that counts failures per IP.
Out of scope for M17.

### Secrets rotation

Changing `JWT_SECRET` invalidates every issued token. There is no
dual-key rotation window.

**Adding it later:** sign with `kid` in the header, keep two keys, verify
against both. Out of scope for M17.

### A `/health` that reads the database

The current `/health` returns `{status: "ok"}` without touching the
database. It cannot detect a database outage. Intentional: the health
check exists so Docker and load balancers know the process is alive, and
adding DB checks makes the healthcheck fail transiently during normal
migrations.

**Adding it later:** `GET /health/ready` that opens a connection and runs
`SELECT 1`. Out of scope for M17.

## Testing this milestone

    cd apps/api
    .\.venv\Scripts\python.exe -m pytest tests/test_auth_security.py tests/test_permissions.py tests/test_backup.py tests/test_rbac_audit.py tests/test_audit_immutability.py -q

Expected: ~24 passed.