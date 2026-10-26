# Reverse proxy

How to put BIMGuard behind nginx or Caddy. The proxy is what enforces
per-IP rate limits at the edge, before requests reach the application.

## Why a reverse proxy

The application rate-limits login attempts (M19b). That limit is per account
and per IP, stored in the database, and it is a second line of defence.
The first line is the proxy: it rejects floods before they consume a
database connection, and it absorbs the raw request-rate attacks that no
application-level limiter can see without opening a connection first.

Without a proxy, every request from the internet hits uvicorn. With the
proxy in front, oversized bodies, slowloris connections, and obvious
floods are stopped before they reach the app.

## Choose nginx or Caddy

Both configurations are shipped and tested. Neither is better than the
other for BIMGuard's needs.

- **nginx** — battle-tested, verbose config, familiar to most operators. Uses `limit_req` for rate limiting.
- **Caddy** — shorter config, automatic HTTPS with Let's Encrypt, modern defaults. Uses the `rate_limit` directive.

If you already run one of them in your environment, use that one.

## Local testing (self-signed certs)

Generate certs once:

    powershell -ExecutionPolicy Bypass -File scripts\generate-dev-certs.ps1

This writes `deploy/nginx/certs/server.crt` and `.key`, and the same under
`deploy/caddy/certs/`. Both proxy options are wired to read from their own
directory, so generating once covers both.

If `openssl` is not in PATH, the script prints installation options and
the `mkcert` equivalent (which auto-trusts the cert so browsers do not
warn). Either approach works.

Start the stack with nginx:

    docker compose -f docker-compose.yml -f docker-compose.proxy-nginx.yml up -d

Or with Caddy:

    docker compose -f docker-compose.yml -f docker-compose.proxy-caddy.yml up -d

Verify:

    Invoke-WebRequest https://localhost/health -SkipCertificateCheck | Select StatusCode

Expect `200`. The browser (or `Invoke-WebRequest`) will warn about the
self-signed cert until you accept it once.

## What the proxy enforces

| Layer | Where | What |
| :--- | :--- | :--- |
| `limit_conn` (nginx) / conn limits | proxy | 20 concurrent connections per IP |
| `/auth/login` rate | proxy | 5 req/min sustained, 3 burst → 8 in the first minute |
| general API rate | proxy | 60 req/min sustained, 20 burst |
| `/health` | proxy | no rate limit (monitoring must always work) |
| client body limit | proxy | 60 MB (above app's 50 MB to allow multipart overhead) |
| `/auth/login` per email | app (M19b) | 5 failed attempts / 15 min |
| `/auth/login` per IP | app (M19b) | 20 failed attempts / 15 min |

The two layers work together. An attacker cannot get past either:

- **Burst attack** (100 req/s from one IP): stopped by the proxy in the
  first second.
- **Slow accumulation** (5 attempts/min for an hour from one IP): stopped
  by the app's per-IP limit after 20 failed logins in 15 minutes.
- **Distributed brute force** (1 attempt/min from 100 IPs): the app's
  per-account limit (5 failures / 15 min for a given email) stops this
  even though no single IP looks suspicious.

## The one thing to get right: X-Forwarded-For

The application's rate limiter reads the client IP from `X-Forwarded-For`
**when `TRUST_PROXY_HEADERS=true`** (which the compose override sets).
The app's `get_client_ip()` takes the **first** entry of that header.

For the app to see the real client IP, the proxy must produce a header
whose first entry is the actual client. Two ways:

1. **REPLACE the header** with the client IP the proxy saw. This is what
   both shipped configs do (`proxy_set_header X-Forwarded-For $remote_addr`
   in nginx; Caddy does this by default). This is correct for a single
   proxy in front of the app.
2. **APPEND to the header** with `$proxy_add_x_forwarded_for`. This
   produces `<client-supplied>, <real-client-ip>` — the app then trusts
   the spoofed first entry. **Do not do this.**

If a future operator "improves" the nginx config by switching to
`$proxy_add_x_forwarded_for`, per-IP rate limiting becomes bypassable.
That is why the comment in `deploy/nginx/nginx.conf` explicitly says so.

If the proxy is itself behind a CDN or load balancer, the CDN's IP ranges
must be listed in `set_real_ip_from` (nginx) so `$remote_addr` resolves to
the original client. The block is in the config but commented out; enable
it and list your CDN's ranges.

## Production checklist

Before exposing the proxy to the internet:

- [ ] Replace self-signed cert with a real one (Let's Encrypt via Caddy automatic HTTPS, or your company CA)
- [ ] Restrict the API port to loopback:
      Docker Compose 2.24+: uncomment the `ports: !override` block in the compose override
      Older Compose: edit `docker-compose.yml` and change `ports: ["8000:8000"]` to `ports: ["127.0.0.1:8000:8000"]`
- [ ] Confirm the API is NOT reachable at `http://<public-host>:8000`
- [ ] Configure `set_real_ip_from` if behind a CDN
- [ ] Set up log rotation for `/var/log/nginx/` or Caddy's log output
- [ ] Verify the `/health` endpoint is reachable through the proxy without rate limit
- [ ] Monitor for 429 rate in nginx access log (see "Monitoring" below)

## Monitoring

Both proxies log every request. Rate-limited requests are 429s. Track the
ratio of 429s to total requests per hour:

    # nginx, last hour
    docker compose logs proxy --since 1h | grep -c " 429 "

    # or from the access log file inside the container
    docker compose exec proxy sh -c "grep ' 429 ' /var/log/nginx/access.log | wc -l"

Two alert conditions:

- **429 rate > 1% of total** → either a real attack, or a limit too tight for legitimate traffic. Investigate; do not just raise the limit.
- **429 rate > 10% for > 5 minutes** → active flood. Consider blocking the source at the firewall or cloud WAF, not at the proxy (the proxy is already rejecting).

Rate-limited requests should also appear in the app's log if they reach it. The application does not know about proxy-level rate limiting — it only logs its own (M19b) 429s.

## Common failures

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Proxy container exits at startup with "cert not found" | `scripts\generate-dev-certs.ps1` was not run | Run it, then `docker compose ... up -d` again |
| `https://localhost` works but `http://localhost:8000` still works too | API port not restricted to loopback | See production checklist |
| Every login blocks after 5 tries across all users | `TRUST_PROXY_HEADERS` not enabled in the app, so all logins appear from the proxy's IP | Confirm the compose override sets `TRUST_PROXY_HEADERS: "true"`. Restart the api container. |
| All clients are blocked by one user's burst | `X-Forwarded-For` is being appended, so the app trusts the client-supplied IP | Change `$proxy_add_x_forwarded_for` back to `$remote_addr` in the nginx config |
| Health checks fail | `/health` is rate limited | Confirm the `location = /health` block exists and has no `limit_req` |

## What this does NOT cover

- **WAF / DDoS protection.** A reverse proxy on a single host is not a
  DDoS mitigation. For that, use Cloudflare, AWS Shield, or your cloud's
  equivalent.
- **Geographic blocking.** Not configured.
- **Bot detection / CAPTCHA.** Not configured.
- **TLS 1.3 only.** Config allows TLS 1.2 for compatibility. Tighten to
  `ssl_protocols TLSv1.3;` if all clients support it.

These are deployment-environment decisions, not application features.