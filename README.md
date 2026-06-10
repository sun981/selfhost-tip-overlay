# Tip Overlay System

Self-hosted **streamer tip overlay** — a fork-and-own replacement for TipMe. A supporter pays
via **PromptPay** (through **Omise or Stripe** — pick one with `PAYMENT_GATEWAY`) → webhook →
signature-verified → pushed to an **OBS browser-source overlay**. Single machine,
`docker compose`, exposed through a **Cloudflare Tunnel** (outbound only, no inbound port).

**Never-custody:** money flows supporter → your payment gateway (Omise/Stripe) → your own
gateway account. The system never holds, transfers, or stores funds, and stores no card data.

> Naming note: it's a **"Tip"** system, not "Donation" — user-facing text *and* code identifiers
> say Tip/Supporter (Omise prohibits "donations"). Keep it that way.

## Status

PoC is **built and runs**. Security gate (`make verify`) is green: 47 tests + a hard
`pip-audit` CVE check + the `core/`-doesn't-import-`app/` guard.

## Fees & disclaimer

- **This system takes 0%.** No platform cut, no middleman holding funds.
- You still pay your **gateway's own fee** — Thai PromptPay is **1.65%** on both Omise and
  Stripe (VAT on the fee per your gateway's terms and your tax status). By default the fee
  comes out of what the streamer receives.
- **MIT licensed, provided as-is** (see [LICENSE](LICENSE)). This is a **reference
  implementation, not a maintained service** — you own the security of your fork
  (`make verify` is your gate after any change). The deployer is solely responsible for
  gateway KYC/onboarding, taxes, and compliance with their gateway's terms of service.

## Get started

> 🇹🇭 **ไม่ถนัดเรื่องเทคนิค? อ่านคู่มือภาษาไทยทีละขั้น:
> [docs/guides/SETUP.md](docs/guides/SETUP.md)** — มีภาพรวม, ค่าใช้จ่าย, ศัพท์ที่ต้องรู้,
> และวิธีใช้งานประจำวัน ครบในไฟล์เดียว

**macOS — one click:** double-click **`setup.command`**. It asks which gateway you use
(Omise or Stripe) and for its keys, OBS WebSocket password, and domain; generates a
secure overlay token; writes `.env`
(`chmod 600`); prints the exact OBS browser-source URL; and offers to start the stack.
(If a downloaded `.command` is blocked, right-click → **Open**, or run `bash scripts/setup.sh`.)

Prefer the terminal (macOS / Linux)?

```bash
make setup            # same guided wizard: .env + token + OBS URL
docker compose up -d  # backend + frontend + overlay + cloudflared
make verify           # security gate — should be green
```

**Windows, or want to do it by hand:** follow the step-by-step
**[docs/guides/SETUP.md](docs/guides/SETUP.md)** (Omise → Cloudflare → OBS → `.env` → run).
The double-click wizard is macOS/Linux only for now.

OBS browser source (local, token from `.env`):
`http://127.0.0.1:8080/?token=<OVERLAY_TOKEN>`

## Project layout — what you touch vs what you don't

You only ever edit a handful of things. Everything else is machinery the wizard and
`docker compose` drive for you — the long file list looks busy but most of it you ignore.

| You edit | What it controls |
|---|---|
| `setup.command` / `make setup` | first-time setup (writes `.env`) |
| `.env` | your secrets — created by the wizard, **never commit it** |
| `app/settings.json` | banned words, amount tiers, alert sound, retention |
| `app/overlay/style.css` · `app/tip/style.css` | colours / fonts |
| `app/overlay/sounds/` | alert audio |

| Don't touch (machinery / security) | Why |
|---|---|
| `core/` | money + signature-verify path — human-review-only, locked |
| `routes/` · `contracts/` · `main.py` | API wiring |
| `Dockerfile.backend` · `docker-compose.yml` · `nginx/` · `requirements.txt` | build & serving |
| `tests/` · `tools/` · `Makefile` | the `make verify` security gate |

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
