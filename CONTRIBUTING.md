# Contributing

Thanks for your interest. This project has a deliberately narrow scope and a
security-gated workflow — please read this before opening a PR.

## Ground rules

1. **Open an issue before feature PRs.** Scope is locked in
   [docs/design/ARCHITECTURE.md](docs/design/ARCHITECTURE.md) (the `LOCKED` block +
   roadmap). PRs that add out-of-scope features (config UI, card payments, TTS,
   multi-streamer, generic gateway framework, …) will be closed with a pointer to the
   roadmap — an issue first saves everyone the work.
2. **`core/` is human-review-only.** Signature verification, secret loading, charge
   creation, idempotency, replay protection (see §13 of ARCHITECTURE). PRs touching
   `core/` get extra scrutiny and may be rewritten or declined even when functionally
   correct. Keep `core/` diffs minimal and separate from other changes.
3. **`make verify` must be green.** It runs the security-invariant test suite plus a
   hard `pip-audit` CVE gate. A new feature needs tests in `tests/`; a security-relevant
   change needs a test that fails without it. Rebuild first if you touched backend code:
   `docker compose build backend && make verify`.
4. **Naming: "Tip" / "Supporter" — never "Donate/Donation".** Applies to user-facing
   text AND code identifiers (the reason is documented at the top of ARCHITECTURE.md).
5. **Dependencies are pinned exactly.** Bumps are their own PR with a note on why,
   and `pip-audit` must stay clean.
6. **Don't over-engineer.** One concrete instance, built well (SPEC §6). No plugin
   systems, no abstractions for hypothetical futures.

## Dev setup

```bash
git clone https://github.com/sun981/selfhost-tip-overlay.git
cd selfhost-tip-overlay
cp .env.example .env          # tests are hermetic; placeholder values are fine
docker compose build backend
make verify                   # green = you're set up correctly
```

Single test: `pytest tests/<file>::<test>` runs inside the backend image — see
`Makefile` (`PYTEST_RUN`).

## Security issues

**Do not open a public issue or PR for a vulnerability.** Use GitHub's private
vulnerability reporting — see [SECURITY.md](SECURITY.md).

## AI-assisted contributions

Fine — this repo is designed for it (see `AGENTS.md` for the zone map). But you are
the author: review what the AI wrote, keep diffs scoped, and expect `core/` changes
to be held to the human-review rule regardless of who or what wrote them.
