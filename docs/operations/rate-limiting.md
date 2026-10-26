# Rate limiting

Three layers, each catching a different kind of abuse.

## Layer 1 — reverse proxy (M27)

Per-IP limits enforced before the request reaches the app.

| Endpoint | Sustained | Burst |
| :--- | :--- | :--- |
| `/auth/login` | 5 req/min | 3 |
| everything else | 60 req/min | 20 |
| `/health` | unlimited | — |

Configuration in `deploy/nginx/nginx.conf` or `deploy/caddy/Caddyfile`.

This layer stops:

- A single attacker sending thousands of requests per second
- An automated scanner hammering `/auth/login` with a password list
- A runaway client loop in a legitimate app

It does **not** stop a determined attacker rotating IPs. For that, layer 2.

## Layer 2 — application (M19b)

Database-backed per-account and per-IP limits on the login endpoint.

| Scope | Limit | Window |
| :--- | :--- | :--- |
| Failed logins per email | 5 | 15 min |
| Failed logins per IP | 20 | 15 min |

Configuration in `apps/api/app/core/config.py` under `login_rate_limit_*`.

This layer stops:

- A distributed credential-stuffing attack (many IPs, same account)
- Slow accumulation past the proxy's burst tolerance

**The app must be told to trust the proxy's `X-Forwarded-For` header.**
Without this, the per-IP limit applies globally to the proxy's IP instead
of per client. Set `TRUST_PROXY_HEADERS=true` (the compose override sets
this automatically).

The proxy is configured to REPLACE (not append to) `X-Forwarded-For`, so
the app sees the actual client IP as the first entry. See
`docs/operations/reverse-proxy.md` for why this matters.

## Layer 3 — account lockout (not implemented)

A true per-account lockout after N consecutive failures, requiring a
password reset or admin unlock. **Not implemented.** The M19b limiter
allows a correct password to succeed even after 5 failures have been
recorded; lockout would not.

The reason not to implement: a permanent or long-lived account lockout is
a denial-of-service vector — an attacker can lock out any known user by
triggering failures. The 429-with-Retry-After approach (M19b) slows an
attacker without disabling the account. This is standard practice; AWS
IAM, GitHub, and most production systems use throttling, not lockout.

If a future milestone adds lockout, it should:

- Lock the account for a fixed, short window (e.g. 15 min), not permanently
- Notify the legitimate user by email
- Provide a self-service unlock via password reset
- Not apply to `admin` accounts (an admin should always be able to recover access)

## Choosing between proxy and app limits

The proxy catches the fast attacks. The app catches the slow ones. Both
are necessary; neither is sufficient.

If you must disable one (e.g. debugging without the proxy running):

- Without the proxy: the app's per-IP limit is looser (20 / 15 min) but
  still applies. Acceptable for a short window.
- Without the app's limiter: only the proxy's per-IP limit applies. Brute
  force from a small IP pool goes unchecked. Do not leave in this state
  for long.

## What to alert on

Two ratios matter:

- **429 rate > 1% of total requests** → either attack or limits too tight.
  Tune and check.
- **429 rate > 10% for 5+ minutes** → active flood. Escalate to firewall
  or cloud WAF.

Do not alert on absolute 429 counts. Normal traffic produces occasional
429s (a user trying 3 passwords in 10 seconds). The ratio matters.

## What is NOT rate limited

- `/health` — monitoring must always work. Any rate limit here creates a
  false alert on the monitoring system when traffic is highest.
- Authenticated endpoints beyond login — the app does not throttle
  `/projects`, `/documents`, `/validation`, etc. A logged-in user can
  make as many requests as the proxy allows. This is a design choice:
  legitimate users uploading large IFCs, running validations, and
  generating PDFs produce bursty traffic that is not abusive.

If a future need arises to throttle authenticated endpoints, the right
place is per-user (from the JWT subject), not per-IP. Not implemented.

## Recovery after an attack

If a specific IP caused a flood and is now blocked by the proxy:

1. Confirm it is a single attacker, not a shared corporate IP.
2. Check `deploy/nginx/access.log` or `docker compose logs proxy` for the
   429 pattern.
3. If single attacker: add to firewall (`iptables`, `ufw`, or your cloud's
   security group), or to the CDN's block list. Do not rely on the proxy
   alone — a dedicated attacker rotates IPs quickly.
4. If shared corporate IP: the block will resolve itself as the proxy's
   rate limit lets the IP try again after the burst window. Consider
   raising the limits to accommodate shared-IP deployments.

## Configuration reference

nginx:

    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    limit_req_zone $binary_remote_addr zone=api:10m   rate=60r/m;
    limit_conn_zone $binary_remote_addr zone=conn:10m;

    limit_req zone=login burst=3 nodelay;
    limit_req_status 429;

Caddy:

    rate_limit {
        zone login {
            key {remote_host}
            events 5
            window 1m
        }
    }

Application:

    LOGIN_RATE_LIMIT_EMAIL_MAX=5
    LOGIN_RATE_LIMIT_EMAIL_WINDOW_MINUTES=15
    LOGIN_RATE_LIMIT_IP_MAX=20
    LOGIN_RATE_LIMIT_IP_WINDOW_MINUTES=15
    TRUST_PROXY_HEADERS=true