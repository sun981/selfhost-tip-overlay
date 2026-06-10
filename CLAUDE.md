# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo status

The PoC is **built and runs** (`docker compose`). Source: `core/` `app/` `routes/` `contracts/` `main.py`; tests in `tests/`; gate = `make verify` (green). The OBS-overlay money path works end to end in Omise test mode.

## Where the docs live (map)

Markdown docs were reorganized into `docs/` (this index is the source of truth for *where*):

| Doc | Path | What |
|---|---|---|
| Spec (binding) | `docs/design/SPEC.md` | §4 security invariants, §11 success criteria |
| Architecture | `docs/design/ARCHITECTURE.md` | decisions D1–D15, dataflows, Secure Core/Safe Edge, **LOCKED** scope |
| Setup guide | `docs/guides/SETUP.md` | install/deploy (Omise · Cloudflare · OBS · `.env`) |
| Testing guide | `docs/guides/TESTING.md` | `make verify` + manual checks |
| Vibecode guide | `docs/guides/VIBECODE.md` | safely editing tip page + overlay |
| Security audit | `docs/security/SECURITY-REVIEW.md` | pre-open-source audit (point-in-time) |
| Security policy | `SECURITY.md` (root) | how to report a vulnerability |
| Readme | `README.md` (root) | project landing + links |
| AI zone rules | `AGENTS.md` (root), `app/AGENTS.md`, `core/AGENTS.md` | edit-zone guidance |

`reports/` is owned by a separate (user-simulating) agent — do not edit it.

### The two design docs are authoritative
- `docs/design/SPEC.md` — **binding spec**. §4 = NON-NEGOTIABLE security requirements, §11 = PoC success criteria. Treat §4 as invariants, not suggestions.
- `docs/design/ARCHITECTURE.md` — concrete design layer: decisions **D1–D15** (§3), dataflows (§8), security map (§9), Secure Core/Safe Edge (§13). It **supersedes SPEC's *implementation* suggestions** where they differ, but **never overrides SPEC §4 security**.
- When SPEC and ARCHITECTURE conflict on *how* (not on security), ARCHITECTURE wins. Examples: PoC uses **SQLite** not Postgres (D5); PromptPay flow creates charge **server-side with no Omise.js** (D2, SPEC §3 step 3 is outdated for PromptPay).

### Review annotations in the docs
`docs/design/ARCHITECTURE.md` contains review markers from prior sessions — `%%review-claude: ...%%` (Obsidian comments, hidden in reading view) and `🔧[rev YYYY-MM-DD] ...` (applied design changes, tagged `P0#/P1#/P2#`). Grep `🔧` or `%%review` to find them. They are real decisions, not noise.

## What this is

Self-host **streamer tip overlay** that replaces TipMe (shut down). Donor pays via Omise PromptPay → webhook → verify → push to an OBS overlay. Fork-and-own OSS, single machine, docker-compose, Cloudflare Tunnel (outbound only, no inbound port). **Never-custody**: money flows donor → Omise → streamer's own Omise account; the system never holds funds.

## Hard rules that span files (easy to violate)

1. **Naming: "Tip" / "Supporter" everywhere — never "Donate/Donation".** Product = **Tip Overlay System**. Why: Omise prohibited-businesses §1.3 lists "Donations" under banned financial services + Thai เรี่ยไร law. This applies to **both user-facing text AND code identifiers** — the project is open source so identifiers are visible. Current identifiers: `tips` table, `supporter_name`, `TipEvent`, `process_tip`. The OS folder `Donation Selfhost` is a pending *manual* rename (local-only). See the `[!warning] Wording` + `[!success] LOCKED` callouts at top of `docs/design/ARCHITECTURE.md`.

2. **Webhook signature verify is THE critical path** (SPEC §4.1, ARCHITECTURE §8.3, verified against [Omise docs](https://docs.omise.co/api-webhooks)):
   - raw body only (never re-serialize JSON), signed payload = `<Omise-Signature-Timestamp>` + `.` + `<raw_body utf-8>`
   - webhook secret is **base64 → decode before use** as HMAC key; HMAC-SHA256 → hex
   - `Omise-Signature` may carry **comma-separated sigs** (24h rotation) → loop, pass if any matches
   - **`hmac.compare_digest` only**, never `==`; reject (401) if none match; replay window ±5 min on timestamp
   - **Gateway is selectable** (`PAYMENT_GATEWAY=omise|stripe`, since 2026-06-05). Both adapters are Secure Core behind `core/payment/base.py` `PaymentGateway` (→ `WebhookEvent`). The above is **Omise's** scheme. **Stripe** (`core/payment/stripe.py`) keeps the same invariants (compare_digest, replay, 401) but differs: header `Stripe-Signature: t=,v1=` (multiple v1 on rotation), secret `whsec_` used **as-is — NOT base64-decoded**, signed = `<t>.<raw_body>`, events `payment_intent.{succeeded,payment_failed,canceled}`. Stripe PromptPay also requires `billing_details[email]` (adapter uses a placeholder). `secrets.validate` + the startup self-test bind to the selected gateway.

3. **Idempotency = record money ≠ push overlay** (two separate keys). `charge_id` PK guards the money record; `pushed_at IS NULL` guards the overlay push. Never use the status flip as the push retry key — an edge-stage crash after the flip would silently skip re-push (money recorded, never shown).

4. **Amount comes only from the verified charge object**, never from the client (SPEC §4.4). donor name/message are donor-owned text → **escape on render (textContent, not innerHTML)** + length/charset cap at `/api/charge`, not "trusted/verified".

5. **Live gate is at `POST /api/charge`, NOT at the webhook** (D7). Webhook must record regardless of live status — PromptPay is async; rejecting a late payment loses money.

6. **All money stored in satang** (1 THB = 100); divide by 100 only at display. Omise THB **minimum charge is ฿20** (hard limit — cannot go lower).

7. **Secure Core vs Safe Edge** (§13) governs where code lives and what may be AI-edited:
   - `core/` = signature verify, secret load, charge create (skey), idempotency, replay, CORS, startup self-test, payment adapter. **Human-review-only** (§13.5). The `PreToolUse` `core/`-protection hook is **deliberately NOT installed yet** (owner wants `core/` editable for now) — treat `core/` edits as human-review-required by convention.
   - `app/` = overlay/tip look, `process_tip` stages, `settings.json`. **Vibecode-safe.**
   - `contracts/` = stable interfaces (`TipEvent`, `OverlayEvent`). Dependency is one-way: `app/` → `contracts/` ← `core/`; **core never imports app**.
   - Security comes from **structure + server-set CSP + fail-closed startup self-test**, not from author discipline.

## Locked PoC scope (2026-06-03, review round 2) — authoritative

The single source of truth for scope is the **`[!success] LOCKED` block at the top of `docs/design/ARCHITECTURE.md`**. Summary:

- **In PoC:** PromptPay (server-side charge, no Omise.js) · SQLite · overlay **local** (localhost, not via tunnel; OBS is on the same machine) · ingress **path-based** (`/` = tip page, `/webhooks/omise`) · **min ฿20** (Omise hard limit) · `process_tip` runs **one real stage = word-filter** (+ **amount-tiers**, both config-driven from `settings.json`) · **alert sound** (static audio) · post-pay feedback to the donor · config = `settings.json` + CSS theme only (**no config UI** — user edits files).
- **Roadmap (do NOT build now):** card (Omise.js + SRI returns), TTS (provider chosen = Google), **donor-pays-fee toggle**, goal bar / top-tipper, config UI, moderation hold-queue, remote OBS (the seam is already designed).
- **Defaults (use unless told otherwise):** message cap 200 chars · privacy purge 90 days · on reconciliation, do not push to the overlay if `paid_at` is older than ~10 min before startup (still record it).

> **Status:** the PoC is **built and running** (`docker compose`; §11 money path verified in Omise test mode — pay → webhook → recorded → pushed → overlay). The `core/`-protection hook (§13.5) is the one remaining build step, intentionally deferred (owner wants `core/` editable). These docs (SPEC, ARCHITECTURE, CLAUDE) are self-sufficient for a fresh session.

## Commands

Entry points (per `docs/design/ARCHITECTURE.md` §13.3 / `docs/design/SPEC.md` §7):
- `docker compose up -d` — run the full stack (backend, frontend, overlay, db, cloudflared)
- `make verify` (a.k.a. `docker compose run tests`) — runs the SPEC §11 security invariants as a test suite; **green is the ship gate**. Runs `pip-audit` as a **hard gate** (self-bootstrapped `.audit-venv`, fails on any CVE) so green means "no known CVE in current pins"; image scan (`trivy`) is still planned. A broken security invariant must fail the build.
- Single test: `pytest tests/<file>::<test>` — runs inside the backend image (see `Makefile` `PYTEST_RUN`; `tests/` is mounted at runtime).

Backend = Python + FastAPI + uvicorn + httpx; SQLite via SQLAlchemy (`DATABASE_URL`, portable to Postgres); frontend/overlay = vanilla static (no build step); OBS link via `obs-websocket` v5 on `host.docker.internal:4455` (never exposed).

## Definition of done (SPEC §11)

Pay in Omise **test mode** → tip appears on overlay; bad-signature webhook → 401; kill backend mid-charge → reconciliation recovers the missed tip on restart; `<script>` in a message renders as text; start without secrets → refuse to start and say what's missing.

## Deliberately out of scope for PoC (do not build)

Card payments (PromptPay-only first; card later needs Omise.js + SRI), TTS, goal bar / top-tipper, donor-pays-fee toggle, config UI, multi-streamer / hosted SaaS, Docker secrets/Vault, full auth/admin panel, generic gateway framework, remote OBS. Build the one concrete instance well first; extract a template later. Honor SPEC §6's note: **do not over-engineer.** (word-filter, amount-tiers, and alert sound ARE in PoC — see Locked PoC scope above.)
