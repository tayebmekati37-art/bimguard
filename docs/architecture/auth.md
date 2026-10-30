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
## Refresh tokens (M32)

Access tokens are short-lived (60 min by default). To keep users logged in
without re-entering a password, login also returns a refresh token.

### Refresh-token lifecycle

- **Storage** — only the SHA-256 hash is stored. The raw token is returned exactly once, at creation.
- **Family** — every refresh token belongs to a family (one family per login). Rotation keeps the family id; logout revokes the whole family.
- **Rotation** — `POST /auth/refresh` revokes the presented token and issues a new one in the same family.
- **Reuse detection** — presenting a token that is already revoked revokes the entire family. This is a defensive measure: if an attacker stole an old refresh token and uses it, both the attacker and the legitimate user are logged out. Strict by design; documented as an intentional tradeoff.
- **Expiry** — refresh tokens expire after `REFRESH_TOKEN_EXPIRE_DAYS` (default 30). Expiry is per-token; there is no family-level TTL beyond the individual tokens.

### Endpoints

- `POST /auth/login` — form-encoded; returns `{access_token, refresh_token, token_type, expires_in}`
- `POST /auth/refresh` — JSON `{refresh_token}`; returns a new pair
- `POST /auth/logout` — optional JSON `{refresh_token}`; revokes the family of that token, plus the access-token jti

### Concurrent refresh from multiple tabs

If two browser tabs each try to refresh with the same token, only one will succeed. The second hit triggers reuse detection (the token was just revoked by the first) and revokes the family. Both tabs are logged out. This is standard strict rotation behavior, and the frontend mitigates it by memoizing the refresh promise — two concurrent 401s trigger one `/auth/refresh` call, not two.

### Session management (M33)

Users can view and revoke their active sessions (refresh-token families).

### Endpoints

- `GET /auth/sessions` — list the current user's active families. Marks the current one using the `fam` claim added to access tokens by M33.
- `DELETE /auth/sessions/{family_id}` — revoke one family. Returns 404 if the family does not belong to the current user (avoids confirming existence across users).
- `DELETE /auth/sessions?keep_current=true|false` — revoke all families. Default `true` keeps the current device signed in; `false` revokes everything including the current access token's jti.

### Current-session detection

Access tokens issued at login or refresh since M33 carry a `fam` claim (the refresh family id). `GET /auth/sessions` marks the token's own family as current. Tokens issued before M33 have no `fam`; they list sessions without a current marker. `DELETE /auth/sessions?keep_current=true` returns 400 if the caller's token has no `fam` — safer than silently revoking the current session.

The transition window is 60 minutes (access token lifetime). After that, all live tokens carry the claim.

### Session ownership

The family id is a UUID. A user cannot revoke another user's family: the endpoint queries `WHERE family_id = X AND user_id = current_user` and returns 404 if no match. There is no "admin can revoke any session" path — out of scope.

### What this does NOT provide

- **Admin session management** — no admin can see or revoke a user's sessions.
- **Device metadata** — sessions show timestamps and rotation count, not user-agent or IP. Those would need to be captured at login and stored on the family row.
- **Notifications on session revoke** — a user whose session was revoked finds out on the next request (401), not proactively.
- **"Suspicious activity" alerts** — no anomaly detection on session creation.
## What this milestone does NOT provide

- **Per-token revocation UI** — users cannot see or revoke individual refresh tokens; they must use logout (per-family) or a future "log out everywhere" endpoint.
- **Sliding expiry** — the token's `expires_at` is fixed at creation. Rotating does not extend it.
- **Device/session tracking** — the family id is opaque; there is no user-facing device list.
- **Grace window** — strict rotation means a token presented even 1 second after rotation is treated as reuse. A small grace window (accept the just-rotated token for ~30s and return the same successor) is a common refinement; not implemented here because it complicates the family-revocation contract.
## Session management (M33)

Users can view and revoke their active sessions (refresh-token families).

### Endpoints

- `GET /auth/sessions` — list the current user's active families. Marks the current one using the `fam` claim added to access tokens by M33.
- `DELETE /auth/sessions/{family_id}` — revoke one family. Returns 404 if the family does not belong to the current user (avoids confirming existence across users).
- `DELETE /auth/sessions?keep_current=true|false` — revoke all families. Default `true` keeps the current device signed in; `false` revokes everything including the current access token's jti.

### Current-session detection

Access tokens issued at login or refresh since M33 carry a `fam` claim (the refresh family id). `GET /auth/sessions` marks the token's own family as current. Tokens issued before M33 have no `fam`; they list sessions without a current marker. `DELETE /auth/sessions?keep_current=true` returns 400 if the caller's token has no `fam` — safer than silently revoking the current session.

The transition window is 60 minutes (access token lifetime). After that, all live tokens carry the claim.

### Session ownership

The family id is a UUID. A user cannot revoke another user's family: the endpoint queries `WHERE family_id = X AND user_id = current_user` and returns 404 if no match. There is no "admin can revoke any session" path — out of scope.

### What this does NOT provide

- **Admin session management** — no admin can see or revoke a user's sessions.
- **Device metadata** — sessions show timestamps and rotation count, not user-agent or IP. Those would need to be captured at login and stored on the family row.
- **Notifications on session revoke** — a user whose session was revoked finds out on the next request (401), not proactively.
- **"Suspicious activity" alerts** — no anomaly detection on session creation.
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