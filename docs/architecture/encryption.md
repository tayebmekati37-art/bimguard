# Encryption at rest (M24)

## Scope

BIMGuard does **not** encrypt data. This document describes what data exists, what the operator must configure, and what the application does and does not verify. It is an honest answer to a security questionnaire, not a claim of encryption.

## Data inventory

- **Users table** — email, name, bcrypt password hash. PII. High sensitivity.
- **Projects, documents, revisions, BIM elements, validation issues, impact events, audit log** — project metadata and geometry. Medium sensitivity.
- **Original uploaded files** in STORAGE_DIR — IFC, JSON, PDFs. High sensitivity.
- **Backups** in STORAGE_DIR/backups — complete copy of everything. High sensitivity.
- **`.env`** — JWT secret, DB password, AI keys. Critical.
- **JWT access tokens** — in transit only, not persisted.

## What the application does

1. bcrypt password hashing (implemented, tested).
2. A startup check that refuses to start in production/staging if ENCRYPTION_MODE is not set to `infrastructure`. This is an operator declaration, not verification.

## What the application does NOT do

1. No field-level encryption. Any column is plaintext in the database.
2. No transparent encryption in the ORM.
3. No SQLite encryption. The .db file is a standard SQLite file.
4. No encrypted backups. The native backup writes plaintext .db or .dump files.
5. No KMS integration. Keys are not managed by the application.
6. No verification that the operator's encryption claim is true.

## ENCRYPTION_MODE values

- `none` — no at-rest guarantee. Development only. Production startup fails if set.
- `infrastructure` — operator certifies disk or database encryption is configured. Allowed anywhere.

Any other value, empty string, or unrecognised string causes a hard startup failure with a message listing the allowed values. Case and whitespace are ignored.

Setting `infrastructure` does not encrypt anything; it is a declaration. An operator who sets it without configuring encryption gets a false sense of security.

## How to configure, per deployment

### SQLite

SQLite has no built-in encryption. Encrypt the volume containing the .db file and STORAGE_DIR.

- Windows: BitLocker on the volume. Verify with `manage-bde -status C:` showing Protection On.
- macOS: FileVault. Verify with `fdesetup status` showing FileVault is On.
- Linux: LUKS. Verify with `lsblk -f` showing crypto_LUKS on the relevant partition.

Then set ENCRYPTION_MODE=infrastructure in .env.

SQLCipher would encrypt the .db file at the application layer, but it requires a pysqlite3 build change and is not currently supported by BIMGuard.

### PostgreSQL on a managed service

RDS, Azure Database, Cloud SQL all offer encryption at rest as a checkbox or a default. Verify in the provider console. Then set ENCRYPTION_MODE=infrastructure.

### PostgreSQL self-hosted

The Docker volume containing pgdata must live on an encrypted filesystem. If the host disk is LUKS/BitLocker/FileVault encrypted, so is the volume. Verify with the host's encryption status tool. Then set ENCRYPTION_MODE=infrastructure.

pgcrypto column encryption is not supported. BIMGuard queries assume plaintext.

### Docker Compose

The `pgdata` and `uploads` named volumes are Docker-managed and not encrypted by default. Two options:

- Change docker-compose.yml to bind-mount an encrypted host directory:
  `/mnt/encrypted/bimguard/pgdata:/var/lib/postgresql/data` and `/mnt/encrypted/bimguard/uploads:/srv/storage`. Where /mnt/encrypted is LUKS/BitLocker encrypted.
- Or rely on the whole host disk being encrypted (LUKS, BitLocker). Named volumes are then encrypted with it.

Then set ENCRYPTION_MODE=infrastructure.

## Backup encryption

Three backup types exist: POST /admin/backup/native (SQLite .db or pg_dump custom format), POST /admin/backup (JSON dump), and managed Postgres snapshots. All are plaintext as written by the application. Recommended practice:

- Store backups on an encrypted volume.
- Or encrypt at the target (S3 SSE-KMS, Azure Storage encryption, GCS CMEK).
- Or gpg-encrypt before upload.

No backup encryption is implemented in BIMGuard.

## Key management

JWT_SECRET is the only cryptographic secret the app reads. Rotation invalidates all tokens; users sign in again. The startup check refuses the default secret in production.

Encryption keys (BitLocker recovery key, RDS KMS key, LUKS passphrase) are the operator's responsibility. The application has no opinion on them and does not read, store, rotate, or validate them.

## What this milestone delivers

- ENCRYPTION_MODE config setting.
- Startup check that refuses production with mode=none (12 tests in tests/test_encryption_check.py).
- This document.

## What this milestone does NOT deliver

- Application-level encryption.
- Backup encryption.
- KMS integration.
- Verification that the operator's claim is true.

## Honest summary for a security questionnaire

> BIMGuard does not implement application-level encryption at rest. In production, the application refuses to start unless the operator declares ENCRYPTION_MODE=infrastructure, certifying disk or database encryption is configured. Passwords are hashed with bcrypt. Backups are plaintext and must be encrypted by the operator at the destination. JWT secrets are read from the environment. There is no KMS integration, no field encryption, and no verification that the declaration is true.

That is the accurate answer. It is weaker than a full encryption story but it is not false, and the gap list is explicit.