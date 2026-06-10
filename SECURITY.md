# Security Policy

Thanks for helping keep the Tip Overlay System and its self-hosters safe.

## Reporting a vulnerability

**Please report privately — do not open a public issue for security bugs.**

- GitHub → **Security** tab → **Report a vulnerability** (opens a private advisory to the
  maintainers). This is the only reporting channel — there is no public security inbox.

Please include: affected file/endpoint, steps to reproduce, impact, and a suggested fix if
you have one. We aim to acknowledge within **72 hours** and to ship a fix or mitigation for
confirmed high-severity issues as quickly as is practical. Please allow a reasonable
disclosure window before going public.

## What this project is (scope context)

A **self-hosted, single-machine** streamer tip overlay. It is **never-custody**: money flows
supporter → the payment gateway (Omise or Stripe, selected by `PAYMENT_GATEWAY`) → the
streamer's own gateway account. The system never holds, transfers, or stores funds, and
stores no card data. Each deployment is one operator's own box behind a Cloudflare Tunnel
(outbound only, no inbound port).

The highest-value invariants (see `docs/design/SPEC.md` §4, `docs/design/ARCHITECTURE.md` §9) are:
- webhook signature verification of the active gateway (`core/payment/omise.py`,
  `core/payment/stripe.py`, behind `core/payment/base.py`)
- "record money before pushing overlay" two-key idempotency (`core/db/operations.py`)
- amount taken only from the verified charge, never the client
- secrets never logged; startup refuses on missing/placeholder secrets
- server-set CSP + `textContent` rendering (no XSS from supporter name/message)

### In scope
- The webhook / charge / idempotency / reconciliation money path (`core/`, `routes/`)
- Authentication / authorization on the public ingress (overlay token, live gate, rate limit)
- XSS / injection / SSRF / secret leakage / signature-verification bypass
- The Docker / nginx / Cloudflare ingress configuration as shipped in this repo

### Out of scope
- Issues that require an attacker to already control the host or the operator's `.env`
- Vulnerabilities in Omise, Stripe, Cloudflare, OBS, or Docker themselves (report upstream)
- A self-hoster's own misconfiguration that deviates from the documented setup (e.g.
  exposing the origin without the Cloudflare Tunnel, committing their `.env`, or enabling
  `DEV_TEST_TRIGGER=1` in production) — but reports that the **docs/defaults invite** such
  mistakes are welcome.

## For self-hosters (operational hardening)

- Never commit `.env`; `chmod 600 .env`. Rotate `OVERLAY_TOKEN` if it ever appears in a
  screen-share, log, or browser URL bar.
- Keep dependencies current — `make verify` runs a hard `pip-audit` CVE gate; a green build
  means no known CVE in the current pins.
- Leave `DEV_TEST_TRIGGER=0` in production (it bypasses payment + signature verification).

## Freshness

This is a fork-and-own reference implementation, **not a maintained service**. Dependencies
pinned and last full security review: **2026-06** (see `docs/security/SECURITY-REVIEW.md`).
If you fork later than that: bump pins, run `make verify` (hard `pip-audit` CVE gate) and
`make scan`, and only trust a green build — you own the security of your fork.
