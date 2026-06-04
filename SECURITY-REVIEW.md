# Security review — pre-open-source audit (2026-06-04)

Point-in-time review of the Tip Overlay System before making the repo public.
Scope: secret hygiene for publishing, the money path (webhook verify → record → push),
the internet-facing ingress, dependency CVEs. Reviewer read the actual code paths, not
just a diff.

## Verdict

**Safe to open-source — with one must-fix-first.** No live exploitable hole was found, and
secret hygiene is clean (no secrets in tracked files or git history). The one thing that
should block `git push --public` is the **dependency CVEs (F1)**, which the repo's own
`make verify` gate has been silently hiding. Everything else is post-publish hardening.

## Resolution (2026-06-04) — F1, F3, F5 fixed

- **F1 fixed:** bumped `fastapi` 0.115.5→0.136.3 (pulls `starlette` 1.2.1), pinned
  `starlette==1.2.1` explicitly, `python-multipart` 0.0.19→0.0.27, `sse-starlette`
  2.1.3→3.4.4, `pydantic` 2.10.3→2.13.4, `pydantic-settings` 2.6.1→2.14.1, `pytest`
  8.3.4→9.0.3, `pytest-asyncio` 0.24.0→1.4.0. Makefile CVE gate hardened: dropped
  `|| true`, now self-bootstraps `pip-audit` into a cached `.audit-venv` and fails on any
  finding. **Verified:** `make verify` → 31 passed + `pip-audit` "No known vulnerabilities
  found"; backend boots healthy on the new deps.
- **F3 fixed:** overlay-token comparison now uses `hmac.compare_digest` (bytes-encoded) at
  `routes/sse.py` (2 sites) and `routes/dev.py`.
- **F5 fixed:** removed unused `slowapi` pin from `requirements.txt`.
- **Still open (backlog):** F2 (token is a public read credential in the URL), F4 (tip-page
  CSP), F6 (`next_seq` TOCTOU), F7 (rate-limit header). Plus: add `SECURITY.md`.

---

## Must fix BEFORE publishing

### F1 — 7 known CVEs in pinned deps, and the CVE gate never caught them — HIGH
`pip-audit -r requirements.txt` (run 2026-06-04):

| Package | Pinned | CVEs | Fix | Surface |
|---|---|---|---|---|
| `starlette` (transitive via `fastapi==0.115.5`) | 0.41.3 | CVE-2025-54121, CVE-2025-62727, PYSEC-2026-161 | ≥0.49.1 (≥1.0.1 clears all 3) | **internet-facing** (ASGI core) |
| `python-multipart` | 0.0.19 | CVE-2026-24486, CVE-2026-40347, CVE-2026-42561 | 0.0.27 | **internet-facing** (form/multipart parser) |
| `pytest` | 8.3.4 | CVE-2025-71176 | 9.0.3 | test-only (not in prod image) |

Root cause it slipped through: `Makefile` runs `pip-audit -r requirements.txt … || true`,
and `pip-audit` is **not installed** on the host → it prints "command not found" and the
gate passes anyway. So CLAUDE.md / TESTING.md's claim *"green = no known CVE in current
pins"* is currently false.

**Fix:**
1. Bump `python-multipart` → `0.0.27`; bump `pytest` → `9.0.3`.
2. Bump `fastapi` to the current release that vendors `starlette ≥1.0.1` (or at minimum a
   `starlette ≥0.49.1`); verify `sse-starlette==2.1.3` stays compatible. This is a coupled
   bump — **re-run `make verify` (31 tests) after**, don't blind-pin starlette under an
   older fastapi.
3. Make the CVE check a **hard** gate: drop the `|| true`, and make `pip-audit` a required
   tool (install in the test image or CI), so "green" actually means "no known CVE."

---

## Non-findings — these were checked and are SOLID

- **Secrets / publishing hygiene:** `.env` is git-ignored, **never committed** (no history).
  `.env.example` is all `CHANGEME` placeholders; `SETUP.md` uses `xxxx` redactions; no real
  keys, tokens, or the overlay token appear in any tracked file. `.gitignore` covers
  `.env*`, `*.db`, `*.sqlite`.
- **Webhook signature verify** (`core/payment/omise.py`): byte-exact `ts + "." + raw_body`,
  base64-decoded secret, HMAC-SHA256, comma-separated sig loop for rotation,
  `hmac.compare_digest` only, ±300s replay window, missing/non-numeric headers → clean 401
  not 500. Matches SPEC §4.1/§4.2 exactly.
- **Idempotency** (`core/db/operations.py`): two separate keys — `charge_id` guards the money
  record (`UPDATE … WHERE status!='successful'`), `pushed_at IS NULL` guards the overlay push
  (`mark_pushed` returns rowcount; SSE emitted only when rowcount==1). No double-push.
- **Amount from verified charge** (`routes/webhook.py`): overlay amount/name/message come from
  the signed webhook charge object, never the client. Client `/api/charge` amount is the
  donor's own chosen tip (correct).
- **SQL**: every query is parameterized — no injection surface.
- **Startup refuses on bad config** (`core/security/secrets.py`): missing or placeholder
  secrets → `sys.exit(1)` with a message; `CORS_ORIGIN='*'` rejected.
- **Other:** Swagger/redoc disabled; CORS pinned to one origin, `allow_credentials=False`;
  log redaction (`core/security/log.py`) keeps name/message/secrets out of logs; QR proxy
  fetches an **Omise-controlled** URL only (not user-supplied) → no SSRF; dev test-trigger is
  both flag-gated (`DEV_TEST_TRIGGER=1`) and token-gated.

---

## Hardening backlog — fine to iterate on in the open (none block publishing)

### F2 — Overlay token is an internet-facing read credential, passed in the URL — LOW–MED
`frontend.conf` proxies `/api/` to the backend, so `/api/events/overlay?token=…` and
`/api/tips/recent?token=…` are reachable **over the public tunnel** (confirmed this session:
`/api/*` returns 200 through `support.sandaijin.xyz`). Anyone holding the token can read tip
names/messages/amounts from the internet. The token rides in the **query string** → it lands
in nginx/Cloudflare access logs and browser history. Not a breach (high-entropy 256-bit
token, rotatable via `.env`), but: be aware it's public, rotate it if a log leaks, and treat
it as a real credential. (EventSource can't send headers, so query-string is hard to avoid
for the overlay.)

### F3 — Token comparison uses `!=`, not constant-time — LOW (hygiene)
`routes/sse.py:61`, `routes/dev.py:35`, `routes/sse.py:77` compare the overlay token with
plain `!=`. Timing-attack risk is negligible (256-bit token, network jitter dominates,
Python `==` length-checks first), but the **webhook path already uses `compare_digest`** —
match it here for consistency. One-line change each.

### F4 — Public tip page has no CSP, while the local overlay has a strict one — LOW (hardening)
`nginx/frontend.conf` (the internet-facing page) sets `X-Frame-Options` /
`X-Content-Type-Options` / `Referrer-Policy` but **no Content-Security-Policy**;
`nginx/overlay.conf` (local-only) has a strict one. The risk posture is inverted. No live XSS
today — `app/tip/index.html`'s inline script writes only via `.textContent` (no `innerHTML`).
Adopting `script-src 'self'` is real work: the page uses an inline `<script>` block plus two
`onclick="resetForm()"` handlers, which would need externalizing first.

### F5 — `slowapi` pinned but unused — LOW (cleanup)
`requirements.txt` pins `slowapi==0.1.9`, but rate limiting is a custom in-process limiter
(`core/ratelimit.py`); `slowapi` was deliberately dropped. Remove the dep to shrink the
supply-chain surface.

### F6 — `next_seq()` TOCTOU race — LOW (known / already tracked)
A webhook arriving during startup reconciliation can share an `event_seq` with another row
→ one tip could be missed on a reconnect replay. Documented in TESTING.md §C; fix is to
allocate the seq inside the `mark_pushed` UPDATE.

### F7 — Rate-limit key trusts a request header — INFO
`core/ratelimit.py` keys on `CF-Connecting-IP` (falls back to `X-Forwarded-For`). Spoofable
in principle, but Cloudflare sets it authoritatively at the edge and the origin has no inbound
port (tunnel-only), so it's not reachable off-tunnel. Acceptable given the architecture;
revisit if the deployment model ever changes.

---

## Also worth noting for a public repo

- Add a `SECURITY.md` (responsible-disclosure contact) — standard for public projects.
- `.obsidian/` config files are tracked; harmless but unusual to ship.
