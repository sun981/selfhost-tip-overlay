# VIBECODE.md — editing the frontend & overlay safely

You want to change how the **tip page** (what supporters see) and the **overlay** (what
shows on stream in OBS) look and behave. This file tells you exactly which files are yours
to play with, which 4 rules you must not break, and how to see your change live.

> One-line mental model: **looks & layout = yours. Money & security = off-limits.**
> If `make verify` stays green (55 passed), you didn't break anything important.

---

## 1. The map — what you can touch

```
app/
├─ overlay/                  🟢 THE OVERLAY (OBS browser source)
│  ├─ index.html             🟢 card markup + <audio> tag   (keep the 2 IDs below)
│  ├─ overlay.js             🟢 SSE subscriber + renderer    (keep the 2 rules below)
│  ├─ style.css              🟢 card look + slide animation  — go wild
│  └─ sounds/
│     └─ alert.wav           🟢 the chime — replace the file, keep the name
│
├─ tip/                      🟢 THE TIP PAGE (public, via Cloudflare tunnel)
│  ├─ index.html             🟢 the form  (keep the input name= attrs below)
│  └─ style.css              🟢 page look — go wild
│
└─ settings.json             🟢 shipped defaults — prefer overriding in user/settings.json

user/                         🟢 YOURS — survives every update (see user/README.md)
├─ settings.json             🟢 your config overrides (per top-level key)
└─ web/
   ├─ theme.css              🟢 loads over both pages' style.css — go wild here first
   └─ sounds/alert.wav       🟢 your chime — presence of the file overrides the default

contracts/events.py          🟡 the field names overlay.js reads — rename = break. ASK FIRST.
routes/                       🟡 API endpoints (charge / webhook / sse). backend logic.
nginx/*.conf                  🟡 the CSP that constrains your HTML (see Rule 1).
core/                         🔴 security: signature verify, secrets, idempotency. HUMAN-REVIEW-ONLY.
.env                          🔴 secrets. never edit for styling. never commit.
```

🟢 = edit freely · 🟡 = ask first / understand the contract · 🔴 = do not touch

---

## 2. The 4 rules you must not break

These aren't style preferences — break them and the overlay silently shows nothing, or
`make verify` goes red.

### Rule 1 — Everything must be self-hosted & same-origin (strict CSP)
The server sends a strict Content-Security-Policy. The usual vibecode reflexes **fail
silently** (no error popup — the thing just doesn't load):

| ❌ This is blocked | ✅ Do this instead |
|---|---|
| `<script src="https://cdn…">` or inline `<script>…</script>` or `onclick="…"` | put JS in `overlay.js` (already same-origin) |
| inline `style="…"` or `<style>…</style>` | put CSS in `style.css` |
| Google Fonts / any font CDN | download the font into `app/overlay/`, use `@font-face` |
| `<img src="https://…">` / hotlinked image | drop the image in `app/overlay/`, use a **relative** path (or a `data:` URI) |
| external sound URL | local file in `sounds/` only |

Rule of thumb: **relative paths to files you put under `app/overlay/` (or `app/tip/`)**, plus
`data:` URIs for tiny images. Nothing from the internet.

### Rule 2 — Supporter text renders with `textContent`, never `innerHTML`
`supporter_name` and `message` are typed by donors → treat as hostile. `overlay.js` already
uses `textContent` (so `<script>` in a message shows as literal text). If you rewrite the
renderer, **keep `textContent`**. `make verify` has a test that fails if a message could execute.

### Rule 3 — Don't rename the IDs / field names the code depends on
`overlay.js` looks these up by name. Restyle them all you want; don't rename them.

- **Overlay HTML — keep these 2 element IDs** (`app/overlay/index.html`):
  - `id="overlay-container"` — where cards get added
  - `id="alert-sound"` — the `<audio>` element it plays
- **Overlay event fields** the JS reads (set in `contracts/events.py`, 🟡): `amount`,
  `supporter_name`, `message`. Render any of them; renaming needs a core change.
- **Tip-page form — keep these input `name=` attributes** (`app/tip/index.html`):
  `supporter_name`, `amount`, `message` (these get POSTed to `/api/charge`).

### Rule 4 — After every change, `make verify` must stay green
```
make verify        # expect "55 passed" + "OK — core/ does not import app/"
```
Red = you broke a security invariant → **revert that change.** Green = safe.

---

## 3. What the overlay actually receives

When a tip is paid, the backend pushes one JSON event down the SSE stream
(`/api/events/overlay`). `overlay.js` parses it and builds the card:

```json
{ "charge_id": "chrg_test_…", "amount": 300000, "supporter_name": "Sandaijin",
  "message": "gg wp", "event_seq": 7, "tts_audio_url": null }
```

- `amount` is in **satang** — divide by 100 for baht (`300000` → ฿3,000). `overlay.js`
  already does this.
- `message` may be **empty** when the amount is below the "show message" tier — that's
  config, not a bug (see `settings.json` → `amount_tiers.show_message_min`).
- CSS hooks the renderer sets (style these): `.tip-card` (+ `.entering` / `.visible` /
  `.leaving` animation states), `.tip-header`, `.tip-name`, `.tip-amount`, `.tip-message`.

---

## 4. Config without code — `user/settings.json`

Shipped defaults live in `app/settings.json`; put YOUR values in `user/settings.json`
(copy `user/settings.example.json`). Override is per top-level key — to change
anything inside `amount_tiers`, copy the whole `amount_tiers` object.

| Key | What it does |
|---|---|
| `banned_words` | list of words the word-filter blanks out of messages |
| `amount_tiers.show_message_min` | below this (satang), the message is hidden (e.g. `2000` = ฿20) |
| `alert_sound` | sound path (see sound note below) |
| `message_max_length` | char cap on messages (default 200) |
| `privacy_purge_days` | how long tips are kept (default 90) |
| `recon_old_threshold_minutes` | on restart, don't re-push tips older than this |

**Swap the chime (most reliable way):** put your own WAV at `user/web/sounds/alert.wav`
— the overlay picks it over the shipped default automatically, and it survives updates.

---

## 5. See your change live

It depends on *which* file you edited, because of how the stack is wired:

| You edited… | How it's served | To see the change |
|---|---|---|
| `user/web/*` (theme.css, sounds) | **bind-mounted** into nginx | just **reload** the OBS browser source / browser tab. No rebuild. |
| `app/overlay/*` or `app/tip/*` (html/css/js/sound) | **bind-mounted** into nginx | just **reload** the OBS browser source / browser tab. No rebuild. |
| `user/settings.json` | **bind-mounted** into the backend | `docker compose restart backend` |
| `app/settings.json`, `app/stages/*`, any backend `.py` | **baked into the backend image** | `docker compose up -d --build backend` |

Overlay URL to test in a plain browser (token required):
```
http://127.0.0.1:8080/?token=<OVERLAY_TOKEN from .env>
```
(A normal browser tab may stay silent until you click the page once — autoplay block. OBS
browser sources autoplay, so sound works there.)

Fire a test card without paying (dev trigger — local only, see `TESTING.md` B2) to iterate
on the look fast.

---

## 6. When you need a human / the core (🔴 / 🟡)

Ask the owner — don't vibecode these:
- anything in `core/` (signature verify, secrets, charge creation, idempotency)
- renaming fields in `contracts/events.py`
- new API behavior in `routes/` (e.g. a new endpoint)
- the CSP in `nginx/*.conf` (loosening it defeats Rule 1 — there's almost always a
  self-hosted way that keeps it strict)

Full zone rules live in `../../AGENTS.md` (repo root) and `../../core/AGENTS.md`. Security spec = `../design/SPEC.md` §4/§11.
