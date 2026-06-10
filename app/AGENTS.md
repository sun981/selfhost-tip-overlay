# Safe Edge — vibecode-safe zone

Files here are safe to edit: overlay styles/animations, tip page UI, `process_tip` stages, config values in `settings.json` (shipped defaults — a user's own values belong in `user/settings.json`, which overrides per top-level key and survives updates).

Rules:
- Edit `user/settings.json` for a user's config (banned words, amount tiers) — no Python needed; `app/settings.json` is the shipped default
- Edit CSS files for visual changes
- After any change: run `make verify` — if it goes red, revert immediately
- Do NOT import from `core/` directly (use `contracts/` interfaces only)
- Do NOT put secrets or skeys here

`make verify` green = safe to deploy.
