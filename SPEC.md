# Tip Overlay System — PoC Spec

โปรเจกต์: ระบบรับ **tip** สำหรับ streamer แบบ self-host (open source) ใช้ Omise เป็น payment gateway
เป้าหมาย PoC: พิสูจน์ flow ครบวง — donor จ่าย → Omise webhook → verify → push ขึ้น overlay — โดยปลอดภัยและ "เงินไม่หาย"

> **อ่านก่อน (2026-06-03):** เอกสารนี้คือ **binding security spec** — §4 (NON-NEGOTIABLE) + §11 (success criteria) ยังผูกมัดทุกข้อ. แต่ส่วน *implementation* บางจุดของ spec นี้ **ล้าสมัย** — `ARCHITECTURE.md` (โดยเฉพาะ **LOCKED block** บนสุด + decisions D1–D15) คือชั้น concrete ที่ **authoritative** และ override ข้อเสนอ impl ของ spec นี้เมื่อขัดกัน (ไม่ override security §4). ที่ override แล้ว: PromptPay = **สร้าง charge ฝั่ง server ไม่ใช้ Omise.js** (D2), DB = **SQLite** (D5), overlay = **local ไม่ผ่าน tunnel**, wording = **"Tip"** (user-facing). PoC scope เพิ่ม: word-filter + amount-tiers + alert sound.
>
> หมายเหตุสำหรับ agent: นี่คือ PoC ห้าม over-engineer ทำให้ flow หลักทำงานได้จริงและปลอดภัยตามข้อบังคับด้านล่างก่อน ส่วน UI สวยงามเป็นเรื่องรอง

---

## 1. บริบทและข้อจำกัด (ต้องเข้าใจก่อนเริ่ม)

- **เครื่องเดียว**: streamer มีคอม stream เครื่องเดียวที่แรงพอรัน Docker ได้ ทุก service รันบนเครื่องนี้
- **Self-host**: ออกเน็ตผ่าน Cloudflare Tunnel (cloudflared) เท่านั้น ไม่เปิด inbound port
- **Gate ด้วย live status**: หน้า donate เปิดให้จ่ายเฉพาะตอน streamer กำลัง live (เช็คผ่าน OBS WebSocket)
- **Bring-your-own-Omise**: streamer ใช้บัญชี Omise ของตัวเอง ระบบไม่ถือเงิน เงินวิ่ง donor → Omise → บัญชี streamer โดยตรง
- **PromptPay เป็นหลัก** (async, ได้ webhook ปกติ) รองรับ card ด้วยได้

## 2. สถาปัตยกรรม (docker-compose, ทุกอย่างบนเครื่องเดียว)

```
services:
  backend       — FastAPI: webhook receiver, /live-status, reconciliation, push (SSE — D4), ถือ skey/webhook secret + สร้าง charge ฝั่ง server (skey)
  frontend      — static tip page: เช็ค live-status, POST /api/charge → backend สร้าง source+charge (PromptPay, **ไม่ใช้ Omise.js** — D2), แสดง QR
  overlay       — static page เปิดเป็น OBS browser source: subscribe SSE, render (sanitize เสมอ) — **local เท่านั้น ไม่ผ่าน tunnel**
  db            — **SQLite** (D5, schema portable → Postgres): tip records + idempotency + reconciliation cursor
  cloudflared   — Cloudflare Tunnel (outbound only)
```

- backend เชื่อม OBS WebSocket ผ่าน `host.docker.internal:4455`
- endpoint สาธารณะผ่าน tunnel: donate page, webhook, overlay
- endpoint ภายใน (`/live-status` ถ้าใช้ internal เท่านั้น) อย่า expose เกินจำเป็น

## 3. Flow หลัก

1. donor เปิดหน้า donate → frontend เรียก `GET /live-status`
2. ถ้าไม่ live → แสดง "ยังไม่ได้ไลฟ์" ไม่ render form
3. ถ้า live → frontend `POST /api/charge` → **backend สร้าง source+charge ฝั่ง server ด้วย skey** (PromptPay, ไม่โหลด Omise.js — D2) → คืน QR (card รุ่นหลังถึงกลับมาใช้ Omise.js+SRI ด้วย pkey)
4. donor จ่าย → Omise ส่ง `charge.complete` webhook มาที่ backend
5. backend **verify signature** → ดึง amount/metadata จาก payload ที่ verified → เก็บ DB (idempotent) → push ไป overlay
6. overlay แสดง donation (escape ทุก output)
7. ตอน backend start: reconciliation job ดึง charge ที่ successful ตั้งแต่ cursor ล่าสุดมา replay กันพลาดตอนเครื่องดับ

## 4. ข้อบังคับด้านความปลอดภัย (NON-NEGOTIABLE — ทำครบทุกข้อ)

### 4.1 Webhook signature verification (ด่านหลัก)
Omise เซ็น webhook ด้วย HMAC-SHA256 (เมื่อตั้ง webhook secret) ต้อง verify ให้ถูก:
- ใช้ **raw request body** เท่านั้น ห้าม parse JSON แล้ว stringify กลับมาคำนวณ (key order/whitespace เปลี่ยน = signature ไม่ตรง)
- signed payload = `<Omise-Signature-Timestamp>` + `.` + `<raw_body UTF-8>`
- webhook secret เป็น Base64 → **decode ก่อน** ใช้เป็น HMAC key
- คำนวณ HMAC-SHA256 → hex encode → เทียบ
- **constant-time compare** เท่านั้น (เช่น `hmac.compare_digest`) ห้ามใช้ `==`
- header `Omise-Signature` อาจมี **หลาย signature คั่นด้วย comma** (ช่วง secret rotation 24 ชม.) → loop เทียบทุกตัว ผ่านถ้าตรงตัวใดตัวหนึ่ง
- ถ้าไม่ตรงเลย → ตอบ 401 ปฏิเสธ

### 4.2 Replay protection
- ตรวจ `Omise-Signature-Timestamp` ต่างจากเวลาปัจจุบันไม่เกิน window (เช่น 5 นาที) ไม่งั้นปฏิเสธ

### 4.3 Idempotency
- เก็บ `charge.id` เป็น unique key ใน DB ถ้าเคยประมวลผลแล้วข้าม (กัน Omise ส่งซ้ำ + กัน replay ระดับ logic)

### 4.4 ไม่เชื่อ client เรื่องเงิน
- amount / donor name / message **ต้องมาจาก charge object ที่ verified จาก Omise เท่านั้น** ห้ามเอาค่าจาก request ฝั่ง client มาแสดง

### 4.5 Overlay XSS prevention
- ข้อความ donor ทุกตัว = ถือว่า hostile
- render เป็น textContent ไม่ใช่ innerHTML
- CSP เข้มบน overlay (`script-src 'self'`, ไม่มี inline script)
- จำกัดความยาว/charset ของข้อความ donor

### 4.6 Secret management
- secret ทั้งหมดผ่าน env (`.env` + `env_file` ใน compose) ห้าม hardcode
- `.gitignore` + `.dockerignore` กัน `.env`, `*.key`, `*.pem`, tunnel creds ตั้งแต่ commit แรก
- **ห้าม COPY/ARG secret เข้า image** เด็ดขาด
- `chmod 600 .env`
- backend **refuse start** ถ้า secret ไม่ครบหรือยังเป็น placeholder (secure by default)

### 4.7 CORS
- `Access-Control-Allow-Origin` เป็น domain ของ streamer แบบ explicit (อ่านจาก env) **ห้ามใช้ `*`**
- webhook endpoint ไม่พึ่ง CORS (server-to-server)

### 4.8 Network / cert
- ออกผ่าน Cloudflare Tunnel เท่านั้น (cert จัดการโดย Cloudflare ไม่ต้องขอเอง)
- ตั้ง SSL mode = Full, เปิด HSTS + Always Use HTTPS (เป็น manual step ใน guide ไม่ใช่โค้ด)
- (optional) firewall allowlist Omise webhook IPs: `54.169.118.227`, `52.74.199.175`, `18.139.13.19` — เป็นชั้นกรองหยาบ อย่าพึ่งเป็นชั้นเดียว (IP อาจเปลี่ยน)

### 4.9 อื่นๆ
- อย่า log secret / charge object เต็ม / stack trace ไป client
- ปิด debug mode ใน production
- rate limit ที่ webhook + donate endpoint
- pin dependency version (lock file commit) + pin base image ด้วย digest

## 5. Live detection
- backend เชื่อม OBS WebSocket (`obs-websocket` v28+, มี password) เรียก `GetStreamStatus` → `outputActive`
- `/live-status` คืนค่าจากตรงนี้
- live detection เป็น **UX gate ไม่ใช่ security control** → backend ควรเช็ค live status ซ้ำก่อนประมวลผลด้วย (defense in depth)
- OBS WebSocket port 4455 ห้าม expose นอกเครื่อง

## 6. Reconciliation
- ตอน backend start: ดึง charge status `successful` จาก Omise API ตั้งแต่ timestamp cursor ล่าสุดที่เก็บใน DB
- replay เข้า pipeline เดียวกับ webhook (ผ่าน idempotency check) → ไม่ trigger ซ้ำของเก่า
- เก็บ cursor หลังประมวลผลสำเร็จ
- เหตุผล: Omise **ไม่การันตี retry** webhook ที่ fail → ต้องมี fallback นี้กัน donation หายตอนเครื่องดับ

## 7. Deliverables ที่อยากได้จาก PoC
1. `docker-compose.yml` ครบ 5 service ตั้งค่า secure
2. `.env.example` (placeholder + comment เป็น inline doc), `.gitignore`, `.dockerignore`
3. backend (FastAPI): webhook handler (signature verify ครบ 4.1–4.3), `/live-status`, **สร้าง charge ฝั่ง server (skey, PromptPay)**, reconciliation, push **SSE** (D4), startup secret validation, rate-limit key = `CF-Connecting-IP` (หลัง tunnel)
4. frontend **tip page**: live gate + `POST /api/charge` (backend สร้าง charge ฝั่ง server, **ไม่ใช้ Omise.js** — D2) + แสดง QR + poll status + feedback หลังจ่าย. **min ฿20** (Omise hard limit), message cap 200
5. overlay page (**local เท่านั้น, ไม่ผ่าน tunnel**): subscribe SSE (`id:` + Last-Event-ID replay) + render sanitize (textContent) + CSP เข้ม + **alert sound** (static, `media-src 'self'`)
6. **`process_donation` seam (1 stage จริง ใน PoC)**: word-filter (banned-words จาก `settings.json`) + amount-tiers (`< X` ไม่โชว์ข้อความ) — ปรับจาก config
7. `settings.json` + CSS theme (config-over-code, **ไม่มี config UI**) + README/guide: prerequisites + deploy + ตั้ง Cloudflare/OBS/Omise dashboard + test ด้วย Omise test mode ก่อน live

## 8. Tech stack
- Backend: Python + FastAPI + uvicorn + httpx (Omise API)
- DB: **SQLite** สำหรับ PoC (D5) ผ่าน SQLAlchemy + `DATABASE_URL`, schema portable → Postgres. WAL mode
- Frontend/overlay: **vanilla static ไม่มี build step** (D6) — audit ง่าย ไม่ต้องมี node toolchain
- Tunnel: cloudflared (path-based ingress)
- License: **MIT** (D8) + DISCLAIMER ว่าผู้ deploy รับผิดชอบ KYC/ภาษี/เงื่อนไข Omise เอง

## 9. สิ่งที่จงใจตัดออกจาก PoC (อย่าเพิ่งทำ)
- โหมด Vercel/cloud (โฟกัส self-host อย่างเดียว)
- Docker secrets / Vault (ใช้ .env ก็พอสำหรับ PoC ใส่เป็น advanced option ใน docs ทีหลัง)
- ระบบ auth/admin panel เต็มรูปแบบ
- multi-streamer / hosted SaaS
- **card payment** (PromptPay-only ก่อน; card รุ่นหลัง = Omise.js + SRI กลับมา)
- **TTS** (เลือก provider=Google ไว้แล้ว แต่ build รุ่นหลัง), **goal bar / top-tipper**, **donor-pays-fee toggle**, **config UI** (PoC ใช้ settings.json ล้วน), **remote OBS** (seam พร้อม)

## 10. ลำดับแนะนำให้ agent ทำ
1. โครงไฟล์ + compose + env/.gitignore/.dockerignore + startup validation
2. webhook handler + signature verification (ชิ้นสำคัญและพลาดง่ายสุด — ทำให้ถูกก่อน)
3. DB schema + idempotency + reconciliation
4. `/live-status` + OBS WebSocket
5. push mechanism (WS/SSE)
6. frontend donate + overlay
7. README/guide
8. ทดสอบ flow ด้วย Omise test mode

## 11. เกณฑ์ว่า PoC สำเร็จ
- จ่ายเงินใน Omise test mode → donation โผล่บน overlay จริง
- ยิง fake webhook ที่ signature ผิด → ถูกปฏิเสธ 401
- ปิด backend ระหว่างมี charge → เปิดใหม่แล้ว reconciliation ดึง donation ที่พลาดกลับมาได้
- ส่งข้อความ donor ที่มี `<script>` → overlay แสดงเป็น text ไม่รันโค้ด
- start backend โดยไม่ตั้ง secret → refuse start พร้อมบอกว่าขาดอะไร
