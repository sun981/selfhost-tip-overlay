# Tip Overlay System

Self-hosted **streamer tip overlay** — a fork-and-own replacement for TipMe. A supporter pays
via **Omise PromptPay** → webhook → signature-verified → pushed to an **OBS browser-source
overlay**. Single machine, `docker compose`, exposed through a **Cloudflare Tunnel** (outbound
only, no inbound port).

**Never-custody:** money flows supporter → Omise → the streamer's own Omise account. The system
never holds, transfers, or stores funds, and stores no card data.

> Naming note: it's a **"Tip"** system, not "Donation" — user-facing text *and* code identifiers
> say Tip/Supporter (Omise prohibits "donations"). Keep it that way.

## Status

PoC is **built and runs**. Security gate (`make verify`) is green: 32 tests + a hard
`pip-audit` CVE check + the `core/`-doesn't-import-`app/` guard.

## Quick start

Full step-by-step (Omise → Cloudflare → OBS → `.env` → run) is in
**[docs/guides/SETUP.md](docs/guides/SETUP.md)**. The short version:

```bash
cp .env.example .env     # fill in Omise keys, Cloudflare tunnel token, OBS WS password, OVERLAY_TOKEN
docker compose up -d     # backend + frontend + overlay + cloudflared
make verify              # security gate — should be green
```

OBS browser source (local, token from `.env`):
`http://127.0.0.1:8080/?token=<OVERLAY_TOKEN>`

## Documentation

| Doc | What it covers |
|---|---|
| [docs/design/SPEC.md](docs/design/SPEC.md) | Binding spec — §4 security invariants, §11 success criteria |
| [docs/design/ARCHITECTURE.md](docs/design/ARCHITECTURE.md) | Design decisions D1–D15, dataflows, Secure Core / Safe Edge, locked scope |
| [docs/guides/SETUP.md](docs/guides/SETUP.md) | Install & deploy (non-technical, step by step) |
| [docs/guides/TESTING.md](docs/guides/TESTING.md) | How to test — `make verify` + manual checks |
| [docs/guides/VIBECODE.md](docs/guides/VIBECODE.md) | Safely editing the tip page & overlay (what you can change, what you can't) |
| [docs/security/SECURITY-REVIEW.md](docs/security/SECURITY-REVIEW.md) | Pre-open-source security audit (point-in-time) |
| [SECURITY.md](SECURITY.md) | Security policy — how to report a vulnerability |
| [AGENTS.md](AGENTS.md) · [CLAUDE.md](CLAUDE.md) | Guidance for AI coding assistants (edit zones) |

## Stack

Python · FastAPI · uvicorn · httpx · SQLAlchemy (SQLite, portable to Postgres via `DATABASE_URL`)
· vanilla static frontend/overlay (no build step) · nginx · Cloudflare Tunnel · OBS via
`obs-websocket` v5.

## Security

Report vulnerabilities privately — see **[SECURITY.md](SECURITY.md)**. Do not commit `.env`.
Keep `DEV_TEST_TRIGGER=0` in production.
