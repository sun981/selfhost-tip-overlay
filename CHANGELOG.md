# Changelog

Notable changes per release. Update with `git pull && docker compose pull && docker compose up -d` —
your `user/` folder is never touched by updates.

## Unreleased

- **fix(omise): startup reconciliation now actually reads Omise's list.** `list_recent`
  used Stripe-style pagination (`has_more` / `starting_after`) and sent `from` as a unix
  integer. Omise is offset-paginated with ISO 8601 `from`, so recovery stopped after the
  oldest 100 charges (or failed outright). Now: ISO `from`, `offset`/`total` paging,
  successful-only filter, plus tests against Omise's real list shape.
- **security(deps): pydantic-settings 2.14.1 → 2.14.2** (CVE-2026-58203) — weekly CI
  gate was red on this.

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
