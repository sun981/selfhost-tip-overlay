# Safe Edge — vibecode-safe zone

Files here are safe to edit: overlay styles/animations, tip page UI, `process_tip` stages, config values in `settings.json`.

Rules:
- Edit `settings.json` for config (banned words, amount tiers, alert sound) — no Python needed
- Edit CSS files for visual changes
- After any change: run `make verify` — if it goes red, revert immediately
- Do NOT import from `core/` directly (use `contracts/` interfaces only)
- Do NOT put secrets or skeys here

`make verify` green = safe to deploy.
