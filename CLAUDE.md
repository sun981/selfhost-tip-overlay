# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo status: design phase, no code yet

This is **not yet a codebase** — it is an Obsidian vault holding two design docs for a not-yet-built PoC. There is no source code, no build, no tests, and (currently) no git. Do not invent commands or claim things run.

- `SPEC.md` — **binding spec**. §4 = NON-NEGOTIABLE security requirements, §11 = PoC success criteria. Treat §4 as invariants, not suggestions.
- `ARCHITECTURE.md` — concrete design layer: decisions **D1–D15** (§3), dataflows (§8), security map (§9), Secure Core/Safe Edge (§13). It **supersedes SPEC's *implementation* suggestions** where they differ, but **never overrides SPEC §4 security**.
- When SPEC and ARCHITECTURE conflict on *how* (not on security), ARCHITECTURE wins. Examples: PoC uses **SQLite** not Postgres (D5); PromptPay flow creates charge **server-side with no Omise.js** (D2, SPEC §3 step 3 is outdated for PromptPay).

### Review annotations in the docs
ARCHITECTURE.md contains review markers from prior sessions — `%%review-claude: ...%%` (Obsidian comments, hidden in reading view) and `🔧[rev YYYY-MM-DD] ...` (applied design changes, tagged `P0#/P1#/P2#`). Grep `🔧` or `%%review` to find them. They are real decisions, not noise.

## What this is

Self-host **streamer tip overlay** that replaces TipMe (shut down). Donor pays via Omise PromptPay → webhook → verify → push to an OBS overlay. Fork-and-own OSS, single machine, docker-compose, Cloudflare Tunnel (outbound only, no inbound port). **Never-custody**: money flows donor → Omise → streamer's own Omise account; the system never holds funds.

## Hard rules that span files (easy to violate)

1. **Naming: user-facing = "Tip", never "Donate/Donation".** Product = **Tip Overlay System**. Why: Omise prohibited-businesses §1.3 lists "Donations" under banned financial services + Thai เรี่ยไร law. **Internal code identifiers stay conventional** (`donations` table, `donor_name`, `charge`, `process_donation`) — they are not user-facing, not seen by Omise/KYC, and match Omise API vocab; **do not churn them**. Doc product names are renamed already; the OS folder `Donation Selfhost` is a pending *manual* rename (local-only, not a policy risk). See the `[!warning] Wording` + `[!success] LOCKED` callouts at top of ARCHITECTURE.md.

2. **Webhook signature verify is THE critical path** (SPEC §4.1, ARCHITECTURE §8.3, verified against [Omise docs](https://docs.omise.co/api-webhooks)):
   - raw body only (never re-serialize JSON), signed payload = `<Omise-Signature-Timestamp>` + `.` + `<raw_body utf-8>`
   - webhook secret is **base64 → decode before use** as HMAC key; HMAC-SHA256 → hex
   - `Omise-Signature` may carry **comma-separated sigs** (24h rotation) → loop, pass if any matches
   - **`hmac.compare_digest` only**, never `==`; reject (401) if none match; replay window ±5 min on timestamp

3. **Idempotency = record money ≠ push overlay** (two separate keys). `charge_id` PK guards the money record; `pushed_at IS NULL` guards the overlay push. Never use the status flip as the push retry key — an edge-stage crash after the flip would silently skip re-push (money recorded, never shown).

4. **Amount comes only from the verified charge object**, never from the client (SPEC §4.4). donor name/message are donor-owned text → **escape on render (textContent, not innerHTML)** + length/charset cap at `/api/charge`, not "trusted/verified".

5. **Live gate is at `POST /api/charge`, NOT at the webhook** (D7). Webhook must record regardless of live status — PromptPay is async; rejecting a late payment loses money.

6. **All money stored in satang** (1 THB = 100); divide by 100 only at display. Omise THB **minimum charge is ฿20** (hard limit — cannot go lower).

7. **Secure Core vs Safe Edge** (§13) governs where code lives and what may be AI-edited:
   - `core/` = signature verify, secret load, charge create (skey), idempotency, replay, CORS, startup self-test, payment adapter. **Human-review-only**, hook-protected (§13.5). A `PreToolUse` hook (built last) forces user confirmation before editing `core/`.
   - `app/` = overlay/donate look, `process_donation` stages, `settings.json`. **Vibecode-safe.**
   - `contracts/` = stable interfaces (`DonationEvent`, `OverlayEvent`). Dependency is one-way: `app/` → `contracts/` ← `core/`; **core never imports app**.
   - Security comes from **structure + server-set CSP + fail-closed startup self-test**, not from author discipline.

## Locked PoC scope (2026-06-03, review round 2) — authoritative

The single source of truth for scope is the **`[!success] LOCKED` block at the top of ARCHITECTURE.md**. Summary:

- **In PoC:** PromptPay (server-side charge, no Omise.js) · SQLite · overlay **local** (localhost, not via tunnel; OBS is on the same machine) · ingress **path-based** (`/` = tip page, `/webhooks/omise`) · **min ฿20** (Omise hard limit) · `process_donation` runs **one real stage = word-filter** (+ **amount-tiers**, both config-driven from `settings.json`) · **alert sound** (static audio) · post-pay feedback to the donor · config = `settings.json` + CSS theme only (**no config UI** — user edits files).
- **Roadmap (do NOT build now):** card (Omise.js + SRI returns), TTS (provider chosen = Google), **donor-pays-fee toggle**, goal bar / top-tipper, config UI, moderation hold-queue, remote OBS (the seam is already designed).
- **Defaults (use unless told otherwise):** message cap 200 chars · privacy purge 90 days · on reconciliation, do not push to the overlay if `paid_at` is older than ~10 min before startup (still record it).

> **Build handoff:** the PoC will be built by a *fresh* session (Sonnet + advisor) with **none of this chat history**. These three docs (SPEC, ARCHITECTURE, CLAUDE) must be self-sufficient. Build order = SPEC §10. `core/`-protection hook (§13.5) is the **last** step.

## Planned commands (target — not implemented yet)

When the code exists, these are the intended entry points (per ARCHITECTURE §13.3 / SPEC §7):
- `docker compose up` — run the full stack (backend, frontend, overlay, db, cloudflared)
- `make verify` (a.k.a. `docker compose run tests`) — runs the SPEC §11 security invariants as a test suite; **green is the ship gate**. Planned to also run `pip-audit` + image scan (`trivy`) so green means "no known CVE in current pins". A broken security invariant must fail the build.
- Single test: there is no harness yet; when built (FastAPI/pytest), expect `pytest tests/<file>::<test>`.

Backend = Python + FastAPI + uvicorn + httpx; SQLite via SQLAlchemy (`DATABASE_URL`, portable to Postgres); frontend/overlay = vanilla static (no build step); OBS link via `obs-websocket` v5 on `host.docker.internal:4455` (never exposed).

## Definition of done (SPEC §11)

Pay in Omise **test mode** → tip appears on overlay; bad-signature webhook → 401; kill backend mid-charge → reconciliation recovers the missed tip on restart; `<script>` in a message renders as text; start without secrets → refuse to start and say what's missing.

## Deliberately out of scope for PoC (do not build)

Card payments (PromptPay-only first; card later needs Omise.js + SRI), TTS, goal bar / top-tipper, donor-pays-fee toggle, config UI, multi-streamer / hosted SaaS, Docker secrets/Vault, full auth/admin panel, generic gateway framework, remote OBS. Build the one concrete instance well first; extract a template later. Honor SPEC §6's note: **do not over-engineer.** (word-filter, amount-tiers, and alert sound ARE in PoC — see Locked PoC scope above.)
