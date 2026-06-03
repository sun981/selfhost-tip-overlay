# Tip Overlay System — AI Guidelines

## Zone map

| Directory | Zone | Can vibecode? |
|---|---|---|
| `core/` | Secure Core | ❌ Ask user first — hook enforced |
| `contracts/` | Interfaces | ⚠️ Rarely changes — ask first |
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

- `core/` — signature verify, secret handling, idempotency. PreToolUse hook will ask for confirmation.
- `contracts/events.py` — changing field names breaks core ↔ app. Ask first.
- `.env` — never commit, never log

## Security invariants (SPEC §11)

These must always pass:
- Bad webhook signature → 401
- Duplicate charge → no double push
- Replay (old timestamp) → 401
- `<script>` in message → renders as text
- Missing secrets → startup refuses
