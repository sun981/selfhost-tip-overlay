# TESTING.md — how to test the Tip Overlay System

Self-contained test guide. Two layers: **(A) automated gate** (fast, run first) and
**(B) manual checks** for things automation can't cover (browser render, sound, real
Omise). Names are "Tip"/"Supporter" everywhere — never "Donation" (Omise §1.3).

---

## A. Automated gate — `make verify`

Green here = SPEC §11 security invariants hold + `core/` doesn't import `app/`.

```bash
make verify
```

Expected tail:
```
47 passed
OK — core/ does not import app/
=== All checks passed ===
```

Notes / gotchas baked into the Makefile:
- `tests/` is `.dockerignore`d and the backend runs `read_only`, so the gate **mounts**
  `tests/` at runtime and disables the pytest cache. Don't "simplify" it back to a bare
  `pytest tests/` — that fails to collect (this bug hid a real overlay break once).
- Host needs `python3` + Docker. The CVE check is a **HARD gate**: it self-bootstraps
  `pip-audit` into a cached `.audit-venv` and **fails the build** on any finding (no longer
  the old `|| true` no-op). No manual install needed; it does need network on first run.
- Tests are hermetic (force their own env), so they pass regardless of your `.env`.

What the gate covers (maps to SPEC §11):
| §11 criterion | Covered by |
|---|---|
| bad-signature webhook → 401 | `test_integration` TestWebhookEndpoint (+ replay, missing headers) |
| successful charge → recorded + pushed once | `test_successful_charge_recorded_and_pushed` |
| kill mid-charge → reconciliation recovers | `test_reconciliation_and_startup` (fake adapter, idempotent rescan) |
| start without secrets → refuse | `test_missing_secret_refuses_start` (subprocess, exit 1) |
| amount only from verified charge | `test_security_invariants` TestAmountFromCharge |
| rate limit on /api/charge (§4.9) | `TestRateLimit` (403 under limit → 429 over) |
| `<script>` renders as text | **NOT automated** — needs a browser → see B4 |

---

## B. Manual checks (do these in order)

### B0. Bring the stack up
```bash
docker compose up -d
docker compose ps          # backend healthy; overlay published on 127.0.0.1:8080
```
If `127.0.0.1:8080` is unreachable, confirm the overlay port is realized (must be non-empty):
```bash
docker inspect tip-overlay-overlay-1 --format '{{json .NetworkSettings.Ports}}'
```

### B1. Overlay loads in OBS
1. OBS → Sources → **+** → **Browser**
2. URL (token = `OVERLAY_TOKEN` from `.env`):
   ```
   http://127.0.0.1:8080/?token=YOUR_OVERLAY_TOKEN
   ```
3. Width 1920 / Height 1080. Uncheck **"Shutdown source when not visible"**.
4. Wrong/no token → SSE 401 → nothing shows (that's correct).

### B2. Fire a test alert WITHOUT paying (dev trigger)
The dev trigger is **off by default** and **token-gated**. Enable only on your local
machine; **never in production** (it bypasses payment + signature verify).

```bash
# enable
sed -i '' 's/^DEV_TEST_TRIGGER=.*/DEV_TEST_TRIGGER=1/' .env   # macOS; Linux: sed -i '...'
docker compose up -d --build --force-recreate backend

# fire (token REQUIRED). amount in satang (10000 = ฿100)
curl -X POST "http://127.0.0.1:8080/api/dev/test-tip?token=YOUR_OVERLAY_TOKEN&name=Somchai&amount=10000&message=hello"
#   >>> expect a card to slide into the OBS source + a chime <<<

# tier check: below ฿20 hides the message (proves process_tip runs)
curl -X POST "http://127.0.0.1:8080/api/dev/test-tip?token=YOUR_OVERLAY_TOKEN&amount=1000&message=should-be-hidden"
#   >>> card shows, message blank <<<

# disable when done (IMPORTANT)
sed -i '' 's/^DEV_TEST_TRIGGER=.*/DEV_TEST_TRIGGER=0/' .env
docker compose up -d --build --force-recreate backend
curl -X POST "http://127.0.0.1:8080/api/dev/test-tip?token=YOUR_OVERLAY_TOKEN"   # expect 404
```

Sound notes:
- Default chime is `app/overlay/sounds/alert.wav` (replace with your own anytime).
- A plain Chrome tab may stay silent until you click the page once (autoplay block).
  **OBS Browser Source autoplays** → sound works there.

### B3. Full real flow (gateway TEST mode) — the money path
1. Gateway dashboard in **TEST mode**; test keys in `.env` (`PAYMENT_GATEWAY` matches).
2. Open the tip page (your Cloudflare Tunnel URL) while **OBS is live** (the page only
   shows the form when `GET /api/live-status` is true — fail-closed if OBS WS is down).
3. Enter name + message + amount **≥ ฿20** → get the PromptPay test QR.
4. Simulate payment — **Omise:** dashboard → charge → "Mark as paid". **Stripe:** open the
   test QR's link → "Authorize Test Payment" (or `stripe trigger payment_intent.succeeded`
   with the CLI). Webhook fires → card appears in OBS.

### B4. §11 manual security checks
- **XSS renders as text:** send a tip whose message is `<script>alert(1)</script>` (or via
  the dev trigger). The overlay must show the literal text, **not** run it. (Server-set CSP
  `script-src 'self'` + `textContent` rendering.)
- **Bad signature → 401:** `curl -X POST http://127.0.0.1:8080/webhooks/omise -d '{}'` → 401.
- **No secrets → refuse start:** blank a required var in `.env` (e.g. `OMISE_SECRET_KEY`),
  `docker compose up -d --force-recreate backend`, check `docker compose logs backend` →
  it prints what's missing and exits. (Restore `.env` after.)

---

## C. Status — verified vs not

- ✅ Automated gate green (47 tests), `make verify` runs end-to-end.
- ✅ Overlay reachable on `127.0.0.1:8080`; SSE wire format correct (single `id:`/`data:`);
  dev trigger fires through `process_tip`; `/api/charge` returns 403/429 (not 422).
- ✅ `next_seq` TOCTOU race (F6) **fixed**: `event_seq` is allocated inside the
  `mark_pushed` UPDATE itself, so concurrent webhook + reconciliation can't collide.
- ✅ Stripe webhook signature verified against a real Stripe CLI trigger
  (`payment_intent.succeeded` → 200 + recorded + pushed; forged/missing sig → 401).
- ⚠️ **Browser render of a card + sound has NOT been eyeballed** — do B1+B2 to confirm.
- ⏳ `core/`-protection hook (ARCHITECTURE §13.5) intentionally still not installed (it's the
  last build step, by design).
