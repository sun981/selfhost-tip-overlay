# Tip Overlay System — AI Guidelines

## Zone map

| Directory | Zone | Can vibecode? |
|---|---|---|
| `core/` | Secure Core | ❌ Ask user first — human-review-only (the PreToolUse hook from ARCHITECTURE §13.5 is **not installed yet**; this is convention, still binding) |
| `contracts/` | Interfaces | ⚠️ Rarely changes — ask first |
| `routes/` · `main.py` | Core-adjacent wiring | ⚠️ Thin glue; webhook/charge routes delegate into `core/` — treat edits like core, ask first |
| `app/stages/` | Safe Edge | ✅ |
| `app/tip/` | Safe Edge | ✅ |
| `app/overlay/` | Safe Edge | ✅ |
| `app/settings.json` | Config | ✅ Config-only changes |
| `tests/` | Tests | ✅ |

## Always run after any change

```
make verify
```

If it goes red → revert. Green = security invariants pass.

## Quick config (no code needed)

- Change banned words → edit `app/settings.json` `banned_words`
- Change amount tier → edit `app/settings.json` `amount_tiers.show_message_min` (in satang)
- Change alert sound → edit `app/settings.json` `alert_sound` path, put file in `app/overlay/sounds/`
- Change overlay style → edit `app/overlay/style.css`
- Change tip page style → edit `app/tip/style.css`

## What NOT to touch

- `core/` — signature verify, secret handling, idempotency. Human-review-only by convention (no enforcing hook yet — see ARCHITECTURE §13.5).
- `contracts/events.py` — changing field names breaks core ↔ app. Ask first.
- `.env` — never commit, never log

## Security invariants (SPEC §11)

These must always pass:
- Bad webhook signature → 401
- Duplicate charge → no double push
- Replay (old timestamp) → 401
- `<script>` in message → renders as text
- Missing secrets → startup refuses

## Where the docs live

Markdown docs are under `docs/`:
- `docs/design/SPEC.md` — binding spec (§4 security, §11 success criteria)
- `docs/design/ARCHITECTURE.md` — decisions D1–D15, Secure Core/Safe Edge, LOCKED scope
- `docs/guides/SETUP.md` — install/deploy · `docs/guides/TESTING.md` — `make verify` + manual checks
- `docs/guides/VIBECODE.md` — safely editing the tip page + overlay
- `docs/security/SECURITY-REVIEW.md` — security audit · `SECURITY.md` (root) — disclosure policy
- `README.md` (root) — project landing · `core/AGENTS.md` / `app/AGENTS.md` — per-zone rules

`reports/` is owned by a separate (user-simulating) agent — do not edit it.
