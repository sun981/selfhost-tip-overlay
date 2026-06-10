#!/usr/bin/env bash
#
# Tip Overlay System — first-time setup wizard (macOS / Linux).
#
# Walks you through filling in .env: prompts for each secret, auto-generates a
# secure OVERLAY_TOKEN, writes .env with chmod 600, and prints the exact OBS
# browser-source URL to paste. Optionally starts the stack and checks the
# backend self-test.
#
# This is a CONFIG helper only — it lives in scripts/, never touches core/, and
# does not weaken anything. The backend's fail-closed startup self-test
# (core/security) is still the real gate: a bad .env makes the backend refuse
# to start regardless of this wizard.
#
# Run:  bash scripts/setup.sh     (or double-click setup.command on macOS)
# Test: ENV_OUT=/tmp/test.env bash scripts/setup.sh   # writes a throwaway file
#
# Written for bash 3.2 (macOS default) — no associative arrays, no ${x,,}.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

TEMPLATE="$REPO_ROOT/.env.example"
ENV_FILE="${ENV_OUT:-$REPO_ROOT/.env}"
TESTING=0
[ -n "${ENV_OUT:-}" ] && TESTING=1

OBS_URL_BASE="http://127.0.0.1:8080/?token="

# ── helpers ──────────────────────────────────────────────────────────────────

say()  { printf '%s\n' "$*" >&2; }
warn() { printf '  ⚠ %s\n' "$*" >&2; }

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# Mirror core/security/secrets.py placeholder rejection so we never write a value
# the backend will refuse at startup.
is_placeholder() {
  case "$1" in
    CHANGEME*|changeme*) return 0 ;;
  esac
  case "$(lower "$1")" in
    ""|xxx|"..."|todo|replace_me|your_secret_here) return 0 ;;
  esac
  return 1
}

gen_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c 64; echo
  fi
}

# prompt_required <label> <hint>  → sets REPLY_VAL
prompt_required() {
  local label="$1" hint="$2" val=""
  while :; do
    say ""
    say "$label"
    [ -n "$hint" ] && say "  ($hint)"
    printf '> ' >&2
    IFS= read -r val || val=""
    if [ -z "$val" ]; then warn "ต้องใส่ค่า ลองใหม่"; continue; fi
    if is_placeholder "$val"; then warn "ยังเป็น placeholder ใส่ค่าจริง"; continue; fi
    break
  done
  REPLY_VAL="$val"
}

# prompt_optional <label> <hint>  → sets REPLY_VAL (may be empty)
prompt_optional() {
  local label="$1" hint="$2" val=""
  say ""
  say "$label"
  [ -n "$hint" ] && say "  ($hint)"
  printf '> ' >&2
  IFS= read -r val || val=""
  REPLY_VAL="$val"
}

confirm_yes() {  # default YES
  local ans=""
  printf '%s [Y/n] ' "$1" >&2
  IFS= read -r ans || ans=""
  case "$(lower "$ans")" in n|no) return 1 ;; *) return 0 ;; esac
}

confirm_no() {   # default NO
  local ans=""
  printf '%s [y/N] ' "$1" >&2
  IFS= read -r ans || ans=""
  case "$(lower "$ans")" in y|yes) return 0 ;; *) return 1 ;; esac
}

# ── preflight ────────────────────────────────────────────────────────────────

[ -f "$TEMPLATE" ] || { say "ไม่พบ .env.example ที่ $TEMPLATE"; exit 1; }

say "============================================"
say " Tip Overlay System — ตัวช่วยตั้งค่า (setup)"
say "============================================"
say "จะถามค่าทีละตัว แล้วสร้างไฟล์ .env ให้"

if [ -f "$ENV_FILE" ]; then
  say ""
  say "พบไฟล์ .env อยู่แล้ว: $ENV_FILE"
  if ! confirm_no "เขียนทับ? (ของเดิมจะถูกสำรองเป็น .env.bak)"; then
    say "ยกเลิก — เก็บ .env เดิมไว้ ไม่มีอะไรเปลี่ยน"
    exit 0
  fi
  cp "$ENV_FILE" "$ENV_FILE.bak"
  say "สำรองของเดิมไว้ที่ $ENV_FILE.bak แล้ว"
fi

# ── collect values ───────────────────────────────────────────────────────────

# Gateway choice first — decides which secrets we ask for.
say ""
say "เลือก payment gateway (ทั้งคู่ใช้ PromptPay server-side):"
say "  1) Omise   — ค่าธรรมเนียม PromptPay 1.65% +VAT"
say "  2) Stripe  — ค่าธรรมเนียม PromptPay 1.65% (VAT ตามสถานะภาษีของบัญชี) + ฿10/refund"
while :; do
  printf '> เลือก [1/2] (default 1): ' >&2
  IFS= read -r g || g=""
  case "$(lower "$g")" in
    ""|1|omise) V_GATEWAY="omise"; break ;;
    2|stripe)   V_GATEWAY="stripe"; break ;;
    *) warn "พิมพ์ 1 หรือ 2" ;;
  esac
done

if [ "$V_GATEWAY" = "stripe" ]; then
  prompt_required "Stripe Secret Key" "sk_test_... หรือ sk_live_... — dashboard.stripe.com → Developers → API keys"
  V_STRIPE_KEY="$REPLY_VAL"
  prompt_required "Stripe Webhook Secret" "whsec_... — Developers → Webhooks → (endpoint) → Signing secret"
  V_STRIPE_WH="$REPLY_VAL"
else
  prompt_required "Omise Secret Key" "skey_test_... (ทดสอบ) หรือ skey_live_... — Omise dashboard → Settings → Keys"
  V_SKEY="$REPLY_VAL"
  prompt_required "Omise Webhook Secret" "สตริงยาวลงท้าย == — Developers → Webhooks → Show secret"
  V_WHSEC="$REPLY_VAL"
fi

prompt_required "OBS WebSocket Password" "ที่ตั้งใน OBS → Tools → WebSocket Server Settings"
V_OBSPW="$REPLY_VAL"

while :; do
  prompt_required "โดเมนของคุณ (CORS_ORIGIN)" "เช่น https://tip.example.com — ไม่มี / ปิดท้าย"
  if [ "$REPLY_VAL" = "*" ]; then warn "ใช้ * ไม่ได้ (ไม่ปลอดภัย) ใส่โดเมนจริง"; continue; fi
  V_CORS="$REPLY_VAL"; break
done

prompt_optional "Cloudflare Tunnel Token" "eyJ... — เว้นว่างได้ถ้ายังไม่ตั้ง tunnel (เติมใน .env ทีหลัง)"
V_TUNNEL="$REPLY_VAL"

say ""
if confirm_yes "สร้าง OVERLAY_TOKEN ให้อัตโนมัติ? (แนะนำ)"; then
  V_TOKEN="$(gen_token)"
  say "  ✓ สร้าง token แล้ว"
else
  prompt_required "OVERLAY_TOKEN" "สตริงสุ่มยาว ≥ 32 ตัว เก็บเป็นความลับ"
  V_TOKEN="$REPLY_VAL"
fi

# ── write .env from template (preserves comments + non-secret defaults) ───────

TMP="$ENV_FILE.tmp.$$"
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    PAYMENT_GATEWAY=*)         printf 'PAYMENT_GATEWAY=%s\n' "$V_GATEWAY" ;;
    OMISE_SECRET_KEY=*)
      if [ -n "${V_SKEY:-}" ]; then printf 'OMISE_SECRET_KEY=%s\n' "$V_SKEY"; else printf '%s\n' "$line"; fi ;;
    OMISE_WEBHOOK_SECRET=*)
      if [ -n "${V_WHSEC:-}" ]; then printf 'OMISE_WEBHOOK_SECRET=%s\n' "$V_WHSEC"; else printf '%s\n' "$line"; fi ;;
    STRIPE_SECRET_KEY=*)
      if [ -n "${V_STRIPE_KEY:-}" ]; then printf 'STRIPE_SECRET_KEY=%s\n' "$V_STRIPE_KEY"; else printf '%s\n' "$line"; fi ;;
    STRIPE_WEBHOOK_SECRET=*)
      if [ -n "${V_STRIPE_WH:-}" ]; then printf 'STRIPE_WEBHOOK_SECRET=%s\n' "$V_STRIPE_WH"; else printf '%s\n' "$line"; fi ;;
    OBS_WS_PASSWORD=*)         printf 'OBS_WS_PASSWORD=%s\n' "$V_OBSPW" ;;
    CORS_ORIGIN=*)             printf 'CORS_ORIGIN=%s\n' "$V_CORS" ;;
    OVERLAY_TOKEN=*)           printf 'OVERLAY_TOKEN=%s\n' "$V_TOKEN" ;;
    CLOUDFLARE_TUNNEL_TOKEN=*)
      if [ -n "$V_TUNNEL" ]; then printf 'CLOUDFLARE_TUNNEL_TOKEN=%s\n' "$V_TUNNEL"
      else printf '%s\n' "$line"; fi ;;
    *) printf '%s\n' "$line" ;;
  esac
done < "$TEMPLATE" > "$TMP"
mv "$TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# ── user/settings.json from template (customization that survives updates) ───

if [ ! -f "$REPO_ROOT/user/settings.json" ] && [ -f "$REPO_ROOT/user/settings.example.json" ]; then
  cp "$REPO_ROOT/user/settings.example.json" "$REPO_ROOT/user/settings.json"
  say "  ✓ สร้าง user/settings.json จาก template (แก้ค่าได้ที่ไฟล์นี้ — รอดทุกอัปเดต)"
fi

say ""
say "============================================"
say " เสร็จ — เขียน .env แล้ว (chmod 600)"
say "============================================"
say ""
say "วาง URL นี้ใน OBS → Sources → + → Browser → URL:"
say ""
say "  ${OBS_URL_BASE}${V_TOKEN}"
say ""
say "Width 1920 · Height 1080 · ✓ Shutdown source when not visible"

# ── optional: start + self-test check (skip in test mode) ────────────────────

if [ "$TESTING" -eq 1 ]; then
  say ""
  say "[test mode] เขียนไป $ENV_FILE — ไม่รัน docker"
  exit 0
fi

say ""
if ! confirm_yes "รันระบบเลยไหม? (docker compose up -d)"; then
  say ""
  say "พร้อมแล้วค่อยรัน:  docker compose up -d"
  exit 0
fi

docker compose up -d
say ""
say "รอ backend ตรวจ self-test..."
result=""
i=0
while [ "$i" -lt 20 ]; do
  logs="$(docker compose logs backend 2>/dev/null || true)"
  case "$logs" in
    *"[Startup self-test] OK"*)  result="ok";   break ;;
    *"[STARTUP ERROR]"*)         result="err";  break ;;
  esac
  i=$((i + 1))
  sleep 2
done

say ""
case "$result" in
  ok)
    say "✅ พร้อมใช้งาน — เปิด $V_CORS เพื่อทดสอบ (ต้อง Start Streaming ใน OBS ก่อน)"
    [ -z "$V_TUNNEL" ] && say "   หมายเหตุ: ยังไม่ได้ตั้ง Cloudflare tunnel token — ตั้งใน .env ก่อน Omise webhook ถึงจะส่งเข้ามาได้" ;;
  err) say "❌ backend แจ้ง error — ดูรายละเอียด:  docker compose logs backend" ;;
  *)   say "⏳ ยังไม่เห็นผล self-test — เช็คเอง:  docker compose logs backend" ;;
esac
