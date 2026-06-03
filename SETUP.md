# คู่มือติดตั้ง Tip Overlay System

> ทดสอบด้วย **Omise test mode** ก่อนเสมอ ก่อนใช้ live key จริง

---

## สิ่งที่ต้องมีก่อนเริ่ม

| สิ่งที่ต้องมี | หมายเหตุ |
|---|---|
| Windows/Mac ที่รัน OBS | เครื่องเดียวกับที่ติดตั้งระบบนี้ |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | ติดตั้งและ**เปิดค้างไว้**ตลอดเวลาใช้งาน |
| Domain บน Cloudflare | ซื้อจาก registrar ใดก็ได้ แล้ว nameserver ชี้มา Cloudflare |
| บัญชี [Omise](https://www.omise.co/) | สมัครฟรี, KYC = บัตรประชาชนหรือใบขับขี่ |
| OBS Studio เวอร์ชัน 28 ขึ้นไป | ดูเวอร์ชัน: Help → About OBS Studio |

---

## ขั้นตอนที่ 1 — ตั้งค่า Omise

### 1.1 สมัครบัญชี Omise

1. ไปที่ [dashboard.omise.co](https://dashboard.omise.co) → **Sign up**
2. ยืนยันอีเมล
3. Dashboard → **Settings** → KYC → อัปโหลดบัตรประชาชนหรือใบขับขี่
4. รอ Omise อนุมัติ (~15 วันทำการ) — แต่ **test mode ใช้ได้ทันที** ไม่ต้องรอ

> ⚠️ ใช้บัญชี Omise สำหรับ tip นี้เท่านั้น ไม่ปนกับธุรกิจอื่น

### 1.2 คัดลอก Secret key (test mode)

1. Dashboard ด้านซ้ายบน → toggle เลือก **Test** (แถบสีเหลือง)
2. เมนูซ้าย → **Settings** → **Keys**
3. คัดลอก **Secret key** — ขึ้นต้นด้วย `skey_test_...`
   - คลิก 👁 เพื่อดู แล้วคัดลอกทั้งบรรทัด

### 1.3 สร้าง Webhook

1. เมนูซ้าย → **Developers** → **Webhooks** → **+ New webhook**
2. ใส่ URL: `https://yourdomain.com/webhooks/omise`
   (แทน `yourdomain.com` ด้วย domain จริงของคุณ)
3. Events → ติ๊ก ✅ **charge.complete**
4. กด **Create**
5. คลิกที่ webhook ที่สร้าง → **Show secret** → คัดลอก Webhook Secret ทั้งหมด

> Webhook Secret เป็นตัวอักษรยาวๆ ลงท้ายด้วย `==` — เก็บไว้ใส่ในไฟล์ config ขั้นตอนที่ 4

---

## ขั้นตอนที่ 2 — ตั้งค่า Cloudflare Tunnel

Cloudflare Tunnel ทำให้ Omise ส่ง webhook มาถึงเครื่องคุณได้ โดยไม่ต้องเปิด port

### 2.1 สร้าง Tunnel

1. ไปที่ [one.dash.cloudflare.com](https://one.dash.cloudflare.com) → **Networks** → **Tunnels**
   (ถ้าหน้าแรกถามว่าเลือก plan → เลือก **Free**)
2. **Create a tunnel** → ตั้งชื่อ เช่น `tip-web` (tunnel นี้รับ traffic จาก internet ไม่เกี่ยวกับ OBS) → **Save tunnel**
3. หน้าถัดไป เลือก tab **Docker** → คัดลอก command ที่มี token ยาวๆ

   ตัวอย่าง:
   ```
   docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token eyJhIjoiXXXXXX...
   ```
   **คัดลอกแค่ส่วน token** หลัง `--token ` (ตัวอักษร `eyJ...` ไปจนสุด)

4. กด **Next** ผ่านหน้านี้ไปก่อน (ไม่ต้องรัน command นั้น)

### 2.2 ตั้ง Public Hostname

1. หลัง create tunnel เสร็จ → คลิกชื่อ tunnel → **Edit** → tab **Public Hostname**
2. **Add a public hostname**:
   - Subdomain: ว่างไว้ (ไม่ต้องใส่)
   - Domain: เลือก domain ของคุณ
   - Service Type: **HTTP**
   - URL: `frontend:80`
3. กด **Save hostname**

> nginx ใน frontend จะส่งต่อ `/api/*` และ `/webhooks/*` ไปหา backend ให้อัตโนมัติ ไม่ต้องตั้งหลาย hostname

### 2.3 ตั้ง SSL บน Cloudflare

1. [dash.cloudflare.com](https://dash.cloudflare.com) → เลือก domain ของคุณ
2. เมนูซ้าย → **SSL/TLS** → **Overview**
3. เปลี่ยน mode เป็น **Full (strict)**
4. **Edge Certificates** (เมนูซ้าย) → เปิด:
   - ✅ **Always Use HTTPS**
   - ✅ **HTTP Strict Transport Security (HSTS)** → Enable → Max Age: 6 months → **Save**

---

## ขั้นตอนที่ 3 — ตั้งค่า OBS WebSocket

1. OBS Studio → เมนูบน **Tools** → **WebSocket Server Settings**
2. ✅ เปิด **Enable WebSocket server**
3. Server Port: `4455` (ค่า default ไม่ต้องแก้)
4. ✅ เปิด **Enable Authentication**
5. ตั้ง **Server Password** — จดไว้ (ใส่ใน .env ขั้นตอนต่อไป)
6. กด **OK**

---

## ขั้นตอนที่ 4 — ติดตั้งและตั้งค่าระบบ

### 4.1 ดาวน์โหลด code

**วิธีที่ 1 — มี Git:**
```bash
git clone https://github.com/yourusername/tip-overlay.git
cd "tip-overlay"
```

**วิธีที่ 2 — ไม่มี Git:**
ไปที่ GitHub → **Code** → **Download ZIP** → แตกไฟล์ → จดตำแหน่งโฟลเดอร์ไว้

### 4.2 สร้างไฟล์ .env

**Mac/Linux:**
```bash
cd /path/to/tip-overlay   # เปลี่ยนเป็น path โฟลเดอร์จริง
cp .env.example .env
chmod 600 .env
```

**Windows (Command Prompt):**
```cmd
cd C:\path\to\tip-overlay
copy .env.example .env
```

### 4.3 แก้ไขไฟล์ .env

เปิด `.env` ด้วย Notepad (Windows) หรือ TextEdit (Mac) แล้วแก้ทุกบรรทัด:

```env
# Omise — ใส่ค่าจากขั้นตอนที่ 1
OMISE_SECRET_KEY=skey_test_xxxxxxxxxxxxxxxx
OMISE_WEBHOOK_SECRET=xxxxxxxxxxxx==

# Cloudflare Tunnel — token จากขั้นตอนที่ 2.1
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoixxxxxxxxxxxxxxxxxxxxxxxx

# OBS WebSocket — password ที่ตั้งในขั้นตอนที่ 3
OBS_WS_HOST=host.docker.internal
OBS_WS_PORT=4455
OBS_WS_PASSWORD=รหัสที่ตั้งใน_OBS

# Domain ของคุณ (ไม่มี / ตัวสุดท้าย)
CORS_ORIGIN=https://yourdomain.com

# Overlay Token — สตริงสุ่มที่คุณตั้งเอง ห้ามบอกใคร
# สร้างได้จาก: https://generate-secret.vercel.app/32
# หรือพิมพ์ตัวอักษร+เลข สุ่มๆ ยาว 32 ตัวก็ได้
OVERLAY_TOKEN=ใส่สตริงสุ่มที่นี่

# ค่าอื่นๆ ไม่ต้องแก้
DATABASE_URL=sqlite:////data/tips.db
TZ=Asia/Bangkok
DEBUG=false
```

> ห้ามใส่ค่า `.env` บน GitHub หรือส่งให้ใคร — ไฟล์นี้มี key ที่เข้าถึงบัญชี Omise ของคุณได้

### 4.4 ตั้ง OBS Browser Source (หน้า overlay)

1. เปิด OBS → scene ที่ต้องการ
2. Sources → **+** → **Browser**
3. ตั้งชื่อ: `Tip Overlay`
4. **URL**: `http://localhost:8080/index.html?token=ใส่ OVERLAY_TOKEN ที่ตั้งใน .env`

   ตัวอย่าง: `http://localhost:8080/index.html?token=abc123xyz456`

5. Width: `1920` · Height: `1080`
6. ✅ **Shutdown source when not visible**
7. ✅ **Refresh browser when scene becomes active**
8. **OK**

### 4.5 รันระบบ

เปิด Terminal (Mac) หรือ Command Prompt (Windows):

```bash
# เข้าโฟลเดอร์โปรเจกต์ก่อนทุกครั้ง
cd /path/to/tip-overlay

# รัน (ครั้งแรกใช้เวลา download image ~2-5 นาที)
docker compose up -d
```

ดู log ว่าพร้อมใช้งาน:
```bash
docker compose logs backend
```

**ต้องเห็นบรรทัดนี้:**
```
[Startup self-test] OK
```

**ถ้าเห็น `[STARTUP ERROR]`** → ดูข้อความต่อว่าขาด env var อะไร → แก้ `.env` → `docker compose restart backend`

---

## ขั้นตอนที่ 5 — ทดสอบ (ทำครบก่อน go live)

### ✅ Test 1: ส่ง tip และดู overlay

1. เปิด OBS → กด **Start Streaming** (ต้องไลฟ์จริงก่อน ระบบจึงเปิดรับ tip)
2. เปิด browser → `https://yourdomain.com`
3. ต้องเห็นฟอร์มกรอก tip (ถ้าเห็น "ยังไม่ได้ไลฟ์" แสดงว่า OBS ต่อถูกแล้ว)
4. กรอกชื่อ + จำนวน (ขั้นต่ำ ฿20) + ข้อความ → ส่ง
5. ต้องเห็น QR code PromptPay
6. จำลองการจ่ายเงิน:
   - Omise Dashboard → **Developers** → เลือก charge ล่าสุด → **Mark as paid** (ปุ่มสีเขียว)
7. ✅ ภายใน ~5 วินาที tip ต้องขึ้นบน OBS overlay

### ✅ Test 2: Webhook ลายเซ็นผิด → ต้องปฏิเสธ

ทดสอบโดยส่ง webhook ปลอมผ่านเครื่องมือ API เช่น [Postman](https://www.postman.com/downloads/) หรือ [Hoppscotch](https://hoppscotch.io):

- Method: `POST`
- URL: `https://yourdomain.com/webhooks/omise`
- Headers:
  - `Content-Type: application/json`
  - `Omise-Signature-Timestamp: 1234567890`
  - `Omise-Signature: invalidsignature`
- Body: `{"key":"charge.complete","data":{}}`

✅ ต้องได้ response **401 Unauthorized**

### ✅ Test 3: Backend ดับระหว่างมี charge pending

1. ส่ง tip → ได้ QR → **ยังไม่สแกน**
2. หยุด backend: `docker compose stop backend`
3. จ่ายเงินจาก Omise dashboard (Mark as paid)
4. เริ่ม backend ใหม่: `docker compose start backend`
5. รอ ~30 วินาที
6. ✅ tip ต้องขึ้น overlay เอง (reconciliation ดึงกลับมา)

### ✅ Test 4: ข้อความ `<script>` ต้องแสดงเป็น text ไม่รัน

1. ส่ง tip พร้อม message: `<script>alert(1)</script>`
2. Mark as paid ใน Omise dashboard
3. ✅ overlay ต้องแสดงข้อความ `<script>alert(1)</script>` ตรงๆ ไม่มี popup

### ✅ Test 5: ไม่มี secret → ไม่ start

1. เปิด `.env` → แก้ `OMISE_SECRET_KEY=` ให้ว่างชั่วคราว
2. `docker compose restart backend`
3. `docker compose logs backend | head -20`
4. ✅ ต้องเห็น `[STARTUP ERROR] Secret validation failed`
5. แก้ `.env` กลับ → `docker compose restart backend`

---

## ขั้นตอนที่ 6 — Switch เป็น Live mode

เมื่อผ่านทุก test แล้วและ Omise อนุมัติ KYC แล้ว:

1. Omise Dashboard → toggle เป็น **Live** (แถบสีเขียว)
2. Settings → Keys → คัดลอก **Live Secret key** (`skey_live_...`)
3. Developers → Webhooks → สร้าง webhook URL เดิม แต่คัดลอก **Live Webhook Secret**
4. แก้ `.env`:
   ```env
   OMISE_SECRET_KEY=skey_live_xxxxxxxxxxxx
   OMISE_WEBHOOK_SECRET=live_secret==
   ```
5. `docker compose restart backend`

> ⚠️ Live key = เงินจริง ตรวจสอบ Test 1–5 ให้ผ่านทุกข้อก่อน switch

---

## ปรับแต่ง

### เปลี่ยนสี/ฟอนต์ overlay
แก้ `app/overlay/style.css` — ไม่ต้อง restart

### เปลี่ยนสี tip page
แก้ `app/tip/style.css` — ไม่ต้อง restart

### ตั้ง banned words และ amount tiers
แก้ `app/settings.json`:
```json
{
  "banned_words": ["คำที่ไม่อยากให้ขึ้น", "คำหยาบ"],
  "amount_tiers": {
    "show_message_min": 5000
  },
  "alert_sound": "sounds/alert.mp3"
}
```
แล้ว: `docker compose restart backend`

### เพิ่มเสียง alert
วางไฟล์ `.mp3` ใน `app/overlay/sounds/` แล้วแก้ `"alert_sound"` ใน settings.json

---

## คำสั่งที่ใช้บ่อย

```bash
# เข้าโฟลเดอร์โปรเจกต์ก่อนทุกครั้ง
cd /path/to/tip-overlay

docker compose up -d          # เริ่มระบบ
docker compose down           # หยุดระบบ
docker compose restart backend  # restart หลังแก้ .env หรือ settings.json
docker compose logs -f backend  # ดู log แบบ real-time (Ctrl+C เพื่อออก)
docker compose ps             # ดูสถานะ service ทั้งหมด
make verify                   # รัน security tests
```

---

## Troubleshooting

| อาการ | สาเหตุที่น่าจะเป็น | วิธีแก้ |
|---|---|---|
| หน้าเว็บขึ้น "ยังไม่ได้ไลฟ์" ตลอด | OBS ไม่ได้ streaming หรือ WebSocket password ผิด | เช็ค OBS → Start Streaming และ password ใน .env |
| QR ไม่ขึ้น | `OMISE_SECRET_KEY` ผิดหรือ test/live mode ไม่ตรง | เช็ค key ใน Omise dashboard |
| tip ไม่ขึ้น overlay หลังจ่าย | Webhook URL ผิดหรือ Cloudflare Tunnel ไม่ได้รัน | `docker compose ps` ดูว่า cloudflared up |
| `[STARTUP ERROR]` | ค่าใน .env ยังเป็น placeholder หรือว่าง | เปิด .env เช็คทุกค่าว่าไม่มี CHANGEME |
| Overlay ไม่ขึ้นใน OBS | token ใน URL ไม่ตรงกับ OVERLAY_TOKEN ใน .env | เช็ค URL ของ browser source |
| Docker ไม่รัน | Docker Desktop ไม่ได้เปิด | เปิด Docker Desktop ก่อน |

---

## หมายเหตุสำคัญ

- **ค่า gateway**: Omise เก็บ PromptPay **1.65% + VAT 7% (≈1.77%)** จากยอดที่ streamer ได้รับ — ระบบนี้ไม่หักเพิ่ม
- **คืนเงินไม่ได้**: PromptPay charge คืนเงินผ่าน Omise ไม่ได้ ควรแจ้ง supporter ก่อนจ่าย
- **ความรับผิดชอบ**: KYC, ภาษี, และการปฏิบัติตามเงื่อนไข Omise เป็นของ streamer เอง ดู [Omise Terms](https://www.omise.co/th/terms)
- **Security**: หากพบช่องโหว่ ดู SECURITY.md
