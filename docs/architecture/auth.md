# Authentication and revocation (M19a)

## Token format

Access tokens are HS256 JWTs. Payload:

    {
      "sub": "<user id>",
      "role": "<role>",
      "exp": <unix seconds>,
      "jti": "<32 hex chars>"
    }

`jti` is a fresh `uuid4().hex` minted on every login. Two logins for the
same user produce two independent sessions.

## What logout invalidates

`POST /auth/logout` inserts one row into `revoked_tokens` with the
token's `jti` as primary key and its `exp` as `expires_at`. Every
protected request then does a single primary-key lookup in `get_current_user`.

**Logout invalidates only the calling session.** Other sessions of the
same user remain valid.

## Migration policy for legacy tokens

Tokens issued before M19a have no `jti`. They cannot be revoked, so they
are rejected with 401. Every active session at deploy time signs in again
once.

## Fail-closed behaviour

If the revocation lookup fails (database unreachable), `get_current_user`
returns **503 Service Unavailable**. Protected routes fail closed. A
logged-out token cannot be resurrected by taking the database down.

## Cleanup

    cd apps/api
    python scripts/cleanup_revoked_tokens.py

Deletes rows where `expires_at < now()`. Safe at any time; an expired
row has no effect because JWT validation already rejects the token.

## What this milestone does NOT provide

- No refresh tokens (the app issues access tokens only)
- No per-user "log out everywhere" endpoint
- No login rate limiting (M19b)
- No object-level authorization audit (M19c)
- No server-side session list UI

## Operational notes

- `JWT_EXPIRE_MINUTES` controls how long a revoked row must persist to
  be useful. The cleanup script uses each row's actual `exp`, not the
  current setting, so it stays correct if the setting changes.
- Deleting from `revoked_tokens` is storage management, not security.