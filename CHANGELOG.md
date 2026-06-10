# Changelog

Notable changes per release. Update with `git pull && docker compose pull && docker compose up -d` —
your `user/` folder is never touched by updates.

## v0.2.0 — 2026-06-10

**Update infrastructure release** — no money-path behavior changes.

- **`user/` folder**: your settings (`user/settings.json`), theme (`user/web/theme.css`),
  and alert sound (`user/web/sounds/alert.wav`) now live outside the upstream tree and
  survive every update. See `user/README.md`. Existing `app/settings.json` edits still
  work but should move to `user/settings.json`.
- **Prebuilt backend image** on ghcr (`ghcr.io/sun981/selfhost-tip-overlay`), published
  by CI on each release tag — updating no longer requires building from source.
- **Schema migrations**: versioned `schema_version` + forward-only runner with automatic
  SQLite backup before any migration. Your `tips.db` carries over untouched (stamped as
  baseline v1).
- deps: websockets 13.1 → 16.0; CI secret-scan fixed on dependabot PRs.

## v0.1.0 — 2026-06-10

First public release. Self-host streamer tip overlay: Omise/Stripe PromptPay →
verified webhook → OBS overlay. Security invariants gated by `make verify`.
