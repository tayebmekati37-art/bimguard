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

## Login rate limiting (M19b)

Failed login attempts are stored in `login_attempts` and used to rate
limit `POST /auth/login`.

| Limit | Default | Configurable |
| :--- | :--- | :--- |
| Failed attempts per email | 5 in 15 min | `LOGIN_RATE_LIMIT_EMAIL_MAX`, `LOGIN_RATE_LIMIT_EMAIL_WINDOW_MINUTES` |
| Failed attempts per IP | 20 in 15 min | `LOGIN_RATE_LIMIT_IP_MAX`, `LOGIN_RATE_LIMIT_IP_WINDOW_MINUTES` |

Either limit triggers `429 Too Many Requests` with a `Retry-After` header
carrying the seconds until the window frees up. The response body does not
reveal whether the email exists.

**Only failed attempts count.** A successful login clears recent rows for
that email, so a typo followed by the correct password does not lock the
user out.

**Storage is the database.** No in-memory cache. The limit works across
multiple workers and survives restarts. Consequence: if the database is
down, the rate-limit check fails and login returns 503 (fail-closed, same
as revocation).

### Client IP

By default `request.client.host` is used. Behind a reverse proxy, set
`TRUST_PROXY_HEADERS=true` so the leftmost `X-Forwarded-For` entry is
used. **Do not enable this without an actual proxy in front of the API**;
the header is client-controlled and turning it on without a proxy lets
attackers spoof their IP and bypass the per-IP limit.

### Cleanup

    cd apps/api
    python scripts/cleanup_login_attempts.py

Deletes rows older than 60 minutes. Safe at any time: rows outside the
window do not affect the limit, so removing them does not change any
outcome.

### What this does NOT provide

- Per-account lockout (an email limit slows an attacker but does not
  permanently disable the account; correct password still works)
- CAPTCHA challenge after failures
- Exponential backoff (fixed window, not sliding or backoff)
- Distributed throttling beyond what the database provides
## What this milestone does NOT provide

- No refresh tokens (the app issues access tokens only)
- No per-user "log out everywhere" endpoint
- No object-level authorization audit (M19c)
- No server-side session list UI

## Operational notes

- `JWT_EXPIRE_MINUTES` controls how long a revoked row must persist to
  be useful. The cleanup script uses each row's actual `exp`, not the
  current setting, so it stays correct if the setting changes.
- Deleting from `revoked_tokens` is storage management, not security.