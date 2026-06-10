# STOP — Secure Core

This directory contains security-critical code: webhook signature verification, secret loading, startup self-test, DB idempotency. **Human review required before any edit.**

Do NOT edit files here without explicit user confirmation.

If you are an AI assistant:
1. Stop before making any change to files in `core/`
2. Explain what you plan to change and why
3. Wait for explicit user approval
4. After any change, run `make verify` — if it goes red, revert

Note: the PreToolUse hook (ARCHITECTURE §13.5) that would enforce this at the tool level is
**not installed yet** — this file is the active guard. The rule above is binding regardless.
