# คู่มือติดตั้ง Tip Overlay System

> ทดสอบด้วย **test mode** ก่อนเสมอ ก่อนใช้ key จริง (ทั้ง Omise และ Stripe)

## ภาพรวม — ระบบนี้ทำงานยังไง

```
ผู้ชมเปิดหน้าเว็บของคุณ → กรอกชื่อ+ข้อความ+จำนวนเงิน → สแกน QR PromptPay จ่าย
        ↓
เงินเข้าบัญชี Omise/Stripe ของคุณโดยตรง (ระบบนี้ไม่แตะเงิน ไม่หักอะไรเพิ่ม)
        ↓
การแจ้งเตือน + ข้อความ เด้งขึ้นบนจอ OBS ของคุณอัตโนมัติ พร้อมเสียง
```

**สิ่งที่ต้องเสียเงิน:** โดเมน (~300–500฿/ปี) อย่างเดียว — ที่เหลือฟรีทั้งหมด
(gateway หักค่าธรรมเนียม ~1.65% ต่อยอด tip ตามปกติของเขา)

**เวลาที่ใช้:** ติดตั้งครั้งแรก ~1–2 ชั่วโมง (ทำครั้งเดียวจบ) · รอ KYC อนุมัติเป็นเรื่องแยก
(ระหว่างรอใช้ test mode ซ้อมได้ทุกอย่าง)

**ลำดับขั้น (ทำตามทีละข้อ ไม่ต้องรีบ):**

| ขั้น | ทำอะไร | ใช้เวลา |
|---|---|---|
| 1 | สมัคร Omise (หรือ Stripe) → เอา key 2 ตัว | ~20 นาที |
| 2 | ตั้ง Cloudflare Tunnel (ทำให้เน็ตเข้าถึงเครื่องคุณแบบปลอดภัย) | ~20 นาที |
| 3 | เปิด WebSocket ใน OBS | ~2 นาที |
| 4 | ดาวน์โหลดระบบ + กรอกค่า + กดรัน | ~20 นาที |
| 5 | ทดสอบด้วยเงินปลอม (test mode) | ~15 นาที |
| 6 | สลับเป็นเงินจริง | ~5 นาที |

> **ศัพท์ที่จะเจอ (อ่านก่อนกันงง):**
> - **Terminal / Command Prompt** = หน้าต่างพิมพ์คำสั่ง — Mac: เปิดแอป "Terminal", Windows: กด Start พิมพ์ `cmd` กด Enter
> - **`.env`** = ไฟล์ข้อความธรรมดา 1 ไฟล์ เก็บรหัสลับทั้งหมดของคุณ (เปิดแก้ด้วย Notepad/TextEdit ได้)
> - **Docker** = โปรแกรมที่รันระบบนี้ให้ ติดตั้งครั้งเดียว เปิดทิ้งไว้ตอนไลฟ์
> - **key / secret / token** = รหัสลับรูปแบบต่างๆ หน้าที่เดียวกันหมด: **คัดลอกมาวาง ห้ามบอกใคร**

---

## สิ่งที่ต้องมีก่อนเริ่ม

| สิ่งที่ต้องมี | หมายเหตุ |
|---|---|
| Windows/Mac ที่รัน OBS | เครื่องเดียวกับที่ติดตั้งระบบนี้ (เครื่องที่ใช้ไลฟ์นั่นแหละ) |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | ดาวน์โหลด → ติดตั้งแบบกด Next ไปเรื่อยๆ → เปิดโปรแกรม รอจนไอคอนวาฬนิ่ง ("Docker Desktop is running") → จากนั้น**เปิดค้างไว้**ทุกครั้งที่ใช้งาน |
| โดเมน (ชื่อเว็บของคุณ) | ดูวิธีซื้อในขั้นตอนที่ 2 — ถ้ายังไม่มี ซื้อตอนนั้นได้เลย |
| บัญชี [Omise](https://www.omise.co/) หรือ [Stripe](https://stripe.com) | สมัครฟรี เลือกเจ้าเดียวพอ, KYC ใช้บัตรประชาชน |
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

## (ทางเลือก) ใช้ Stripe แทน Omise

ระบบรองรับ **Stripe** เป็น gateway ทางเลือก (`PAYMENT_GATEWAY=stripe` — ตัวช่วย `setup.command` จะถามให้เลือก). Stripe ก็ใช้ **PromptPay server-side** เหมือนกัน (ไม่ต้องมี Stripe.js) ค่าธรรมเนียม **1.65% (≈ Omise)**. บุคคลธรรมดาไทยสมัครได้ (บัตร ปชช. + บัญชีธนาคารไทย).

1. สมัคร [dashboard.stripe.com](https://dashboard.stripe.com) → เปิด **Test mode** (มุมขวาบน)
2. **Settings → Payment methods** → เปิด **PromptPay**
3. **Developers → API keys** → คัดลอก **Secret key** (`sk_test_...`)
4. **Developers → Webhooks → + Add endpoint**:
   - Endpoint URL: `https://yourdomain.com/webhooks/stripe`
   - Events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`
   - กด **Add** → คัดลอก **Signing secret** (`whsec_...`)
5. ใส่ใน `.env` (หรือให้ wizard กรอก): `PAYMENT_GATEWAY=stripe` · `STRIPE_SECRET_KEY=sk_...` · `STRIPE_WEBHOOK_SECRET=whsec_...`

> ที่เหลือ (Cloudflare · OBS · รัน) เหมือนกันหมด — ข้ามไปขั้นตอนที่ 2 ได้เลย.

---

## ขั้นตอนที่ 2 — ตั้งค่า Cloudflare Tunnel

Cloudflare Tunnel ทำให้ Omise/Stripe ส่งข้อมูลการจ่ายเงินมาถึงเครื่องคุณได้แบบปลอดภัย โดยไม่ต้องเปิดช่องอะไรในเครื่อง/เราเตอร์เลย

### 2.0 ยังไม่มีโดเมน? ซื้อก่อน (~5 นาที)

โดเมน = ชื่อเว็บที่ผู้ชมจะเปิด เช่น `tip-ชื่อช่องคุณ.com`

**ทางง่ายสุด — ซื้อกับ Cloudflare เลย** (ไม่ต้องตั้ง nameserver เอง):
1. สมัคร [dash.cloudflare.com](https://dash.cloudflare.com) (ฟรี)
2. เมนูซ้าย → **Domain Registration** → **Register Domains** → ค้นหาชื่อที่อยากได้ → จ่ายเงิน (~$10/ปี ≈ 350฿)
3. เสร็จ — โดเมนพร้อมใช้กับขั้นตอนถัดไปทันที

**ถ้ามีโดเมนจากที่อื่นอยู่แล้ว** (Namecheap, GoDaddy ฯลฯ): Cloudflare dashboard → **Add a site** → ใส่ชื่อโดเมน → เลือก plan **Free** → ระบบจะบอก nameserver 2 ตัว → ไปแก้ nameserver ที่เว็บที่คุณซื้อโดเมน → รอจน Cloudflare ขึ้นว่า Active (อาจรอเป็นชั่วโมง)

#### เลือกชื่อโดเมนยังไงให้คุ้ม (คิดก่อนซื้อ 1 นาที)

โดเมน 1 ชื่อ = บ้านออนไลน์ของคุณทั้งหลัง ไม่ใช่แค่หน้า tip — แตก **subdomain**
(ชื่อย่อยหน้าจุด) ได้ฟรีไม่จำกัด ดังนั้น:

- ✅ **ซื้อเป็นชื่อช่อง/ชื่อแบรนด์ของคุณ** เช่น `mochastream.com` — แล้วให้หน้า tip
  อยู่ที่ `tip.mochastream.com` (วิธีตั้งอยู่ในข้อ 2.2)
- ❌ เลี่ยงชื่อที่ล็อกการใช้งานแคบๆ เช่น `tip-mocha.com` หรือ `mocha-donate.com` —
  วันหลังอยากทำเว็บอื่นต้องซื้อใหม่ (และคำว่า donate มีประเด็นกับเงื่อนไข gateway ด้วย)

ตัวอย่างที่โดเมนเดียวกันต่อยอดได้ในอนาคต (ไม่ต้องจ่ายเพิ่ม):
| Subdomain | ใช้ทำอะไร |
|---|---|
| `tip.ชื่อคุณ.com` | หน้า tip (ระบบนี้) |
| `ชื่อคุณ.com` (ตัวหลัก) | เว็บแนะนำตัว / link-in-bio / ตารางไลฟ์ |
| `shop.ชื่อคุณ.com` | ขายของที่ระลึก |
| `clip.ชื่อคุณ.com` | รวมคลิปไฮไลต์ |
| อีเมล `contact@ชื่อคุณ.com` | อีเมลแบรนด์ตัวเอง (Cloudflare Email Routing ฟรี — forward เข้า Gmail ได้) |

> ตั้งหน้า tip ไว้บนตัวหลัก (`ชื่อคุณ.com` เลย ไม่มี subdomain) ก็ได้เหมือนกัน —
> ระบบใช้แค่ path `/` กับ `/webhooks/...` วันหลังค่อยย้ายไป `tip.` แล้วเอาตัวหลัก
> ไปทำเว็บก็ทำได้ (แค่แก้ hostname ในข้อ 2.2 + URL webhook + `CORS_ORIGIN` ให้ตรงกัน)

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
   - Subdomain: ใส่ `tip` (แนะนำ — เก็บตัวหลักไว้ทำอย่างอื่น ดูกล่อง "เลือกชื่อโดเมน" ข้างบน)
     หรือเว้นว่างถ้าอยากใช้ตัวหลัก `ชื่อคุณ.com` ไปเลย
   - Domain: เลือก domain ของคุณ
   - Service Type: **HTTP**
   - URL: `frontend:80`
3. กด **Save hostname**

> nginx ใน frontend จะส่งต่อ `/api/*` และ `/webhooks/*` ไปหา backend ให้อัตโนมัติ ไม่ต้องตั้งหลาย hostname

> ⚠️ **จุดเดียวที่พลาดบ่อย:** ที่อยู่ที่เลือกตรงนี้ (เช่น `tip.ชื่อคุณ.com`) ต้องใช้
> **ตัวเดียวกันเป๊ะ** ในอีก 2 ที่: ① URL webhook ใน dashboard ของ Omise/Stripe
> (ขั้นตอนที่ 1) และ ② ค่า `CORS_ORIGIN` ในไฟล์ `.env` (ขั้นตอนที่ 4) —
> ทุกที่ในคู่มือที่เขียน `yourdomain.com` ให้แทนด้วยที่อยู่นี้

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

**วิธีที่ 1 — ง่ายสุด (ไม่ต้องมีโปรแกรมอะไร):**
ไปที่หน้า GitHub ของโปรเจกต์ → ปุ่มเขียว **Code** → **Download ZIP** → แตกไฟล์ →
ย้ายโฟลเดอร์ไปไว้ที่จำง่ายๆ เช่น Desktop → จดไว้ว่าอยู่ตรงไหน (จะใช้ตลอดคู่มือนี้)

**วิธีที่ 2 — มี Git:**
```bash
git clone https://github.com/sun981/selfhost-tip-overlay.git
cd selfhost-tip-overlay
```

> **ทางลัด (Mac/Linux) — แนะนำ:** แทนขั้นตอน **4.2–4.4** ด้านล่างทั้งหมด ด้วยการ
> **ดับเบิลคลิก `setup.command`** (Mac) หรือรัน `make setup` (Mac/Linux). ตัวช่วยจะ
> ถามค่าทีละตัว สร้าง `OVERLAY_TOKEN` ให้อัตโนมัติ เขียน `.env` (`chmod 600`) และ
> print URL ของ OBS browser source ให้เลย → แล้วข้ามไป **ขั้นตอนที่ 5** ได้
> (ยังต้องตั้ง OBS browser source ตาม URL ที่ wizard ให้). **Windows** ทำตาม 4.2–4.4 ด้านล่าง
> ถ้าดับเบิลคลิก `setup.command` แล้วถูกบล็อก (ดาวน์โหลดมาจากเน็ต) → คลิกขวา → **Open**
> หรือเปิด Terminal แล้วรัน `bash scripts/setup.sh`

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

> **ทริค Windows:** เปิด File Explorer เข้าไปในโฟลเดอร์โปรเจกต์ → คลิกที่แถบ address
> ด้านบน → พิมพ์ `cmd` → Enter — จะได้ Command Prompt ที่อยู่ในโฟลเดอร์นั้นเลย
> ไม่ต้องพิมพ์ `cd` เอง (ใช้ทริคนี้ได้กับทุกคำสั่งในคู่มือนี้)
>
> **หมายเหตุ:** ไฟล์ `.env` อาจมองไม่เห็นใน File Explorer (ชื่อขึ้นต้นด้วยจุด = ไฟล์ซ่อน)
> เปิดด้วย Notepad ผ่านคำสั่ง `notepad .env` ใน Command Prompt ได้เลย

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

# Overlay Token — รหัสลับกันคนอื่นแอบเปิด overlay ของคุณ ตั้งเองได้ ห้ามบอกใคร
# วิธีสร้างแบบสุ่มจริงๆ:
#   Mac:     เปิด Terminal พิมพ์  openssl rand -hex 16
#   Windows: เปิด PowerShell พิมพ์  -join ((48..57)+(97..122) | Get-Random -Count 32 | % {[char]$_})
# หรือพิมพ์ตัวอักษร+เลขมั่วๆ เองยาวๆ 32 ตัวก็ได้ (อย่าใช้คำเดาง่าย)
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

   ตัวอย่าง: `http://localhost:8080/index.html?token=YOUR_OVERLAY_TOKEN`

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
6. จำลองการจ่ายเงิน (test mode ไม่ใช้เงินจริง):
   - **Omise:** Dashboard → **Developers** → เลือก charge ล่าสุด → **Mark as paid** (ปุ่มสีเขียว)
   - **Stripe:** ใน test mode ตัว QR ที่ขึ้นจะเป็น QR ทดสอบ — สแกน/คลิกแล้วจะเจอหน้า
     ของ Stripe ที่มีปุ่ม **Authorize Test Payment** ให้กดจ่ายปลอม
     (หรือ Dashboard → Payments → เลือกรายการ → ดูสถานะ)
7. ✅ ภายใน ~5 วินาที tip ต้องขึ้นบน OBS overlay

### ✅ Test 2: Webhook ลายเซ็นผิด → ต้องปฏิเสธ

เช็คว่าระบบไม่รับข้อมูลการจ่ายเงินปลอม — คัดลอกคำสั่งนี้ทั้งก้อนไปวางใน Terminal /
Command Prompt (แก้ `yourdomain.com` เป็นโดเมนจริงก่อน):

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://yourdomain.com/webhooks/omise -H "Content-Type: application/json" -H "Omise-Signature-Timestamp: 1234567890" -H "Omise-Signature: invalidsignature" -d "{}"
```

✅ ต้องได้เลข **401** (= ระบบปฏิเสธของปลอม ถูกต้องแล้ว)
(ใช้ Stripe → เปลี่ยนท้าย URL เป็น `/webhooks/stripe` ผลต้องได้ 401 เหมือนกัน)

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

## ขั้นตอนที่ 6 — Switch เป็น Live mode (เงินจริง)

เมื่อผ่านทุก test แล้วและ gateway อนุมัติ KYC แล้ว:

**Omise:**
1. Dashboard → toggle เป็น **Live** (แถบสีเขียว)
2. Settings → Keys → คัดลอก **Live Secret key** (`skey_live_...`)
3. Developers → Webhooks → สร้าง webhook URL เดิม แต่คัดลอก **Live Webhook Secret**
4. แก้ `.env`:
   ```env
   OMISE_SECRET_KEY=skey_live_xxxxxxxxxxxx
   OMISE_WEBHOOK_SECRET=live_secret==
   ```
5. `docker compose restart backend`

**Stripe:**
1. Dashboard → ปิด **Test mode** (toggle มุมขวาบน)
2. Developers → API keys → คัดลอก **Live** Secret key (`sk_live_...`)
3. Developers → Webhooks → สร้าง endpoint URL เดิม (`/webhooks/stripe`) ในโหมด live
   → คัดลอก Signing secret (`whsec_...`) ตัวใหม่
4. แก้ `.env`: `STRIPE_SECRET_KEY=sk_live_...` และ `STRIPE_WEBHOOK_SECRET=whsec_...`
5. `docker compose restart backend`

> ⚠️ Live key = เงินจริง ตรวจสอบ Test 1–5 ให้ผ่านทุกข้อก่อน switch
> แนะนำ: ลองโอนจริง ฿20 ของตัวเอง 1 ครั้งหลัง switch เพื่อยืนยันว่าทุกอย่างถึงกัน

---

## การใช้งานประจำวัน (หลังติดตั้งเสร็จ)

ติดตั้งครั้งเดียวจบ — วันไลฟ์ปกติทำแค่นี้:

1. เปิดเครื่อง → เปิด **Docker Desktop** รอไอคอนวาฬนิ่ง (ระบบ tip จะ start ตัวเองอัตโนมัติ)
2. เปิด **OBS** → กด **Start Streaming**
3. แปะลิงก์หน้า tip (`https://yourdomain.com`) ไว้ใต้ไลฟ์/ใน bio ให้ผู้ชมกด
4. จบ — tip ที่จ่ายสำเร็จจะเด้งบนจอเอง เงินเข้าบัญชี gateway ของคุณตรงๆ

สิ่งที่ควรรู้:
- **ปิด OBS / หยุดไลฟ์ = หน้า tip ปิดรับอัตโนมัติ** (ผู้ชมเห็น "ยังไม่ได้ไลฟ์") — แต่ถ้ามีคนสแกน QR ค้างไว้แล้วเพิ่งจ่ายหลังจบไลฟ์ เงินไม่หาย ระบบบันทึกให้เสมอ
- **เครื่องดับ/รีสตาร์ทกลางไลฟ์?** เปิด Docker Desktop กลับมา — ระบบจะไล่เก็บ tip ที่พลาดไปให้เอง (ขึ้นจอเฉพาะรายการใหม่ๆ รายการเก่าเก็บลงประวัติเงียบๆ)
- อยากดูว่าใครเคย tip เท่าไหร่ → ดูใน dashboard ของ Omise/Stripe ได้ตลอด

---

## ปรับแต่ง

ของที่คุณแก้เองอยู่ในโฟลเดอร์ **`user/`** ทั้งหมด — โฟลเดอร์นี้ไม่ถูกแตะตอนอัปเดตระบบ
(ดูรายละเอียดใน `user/README.md`)

### ตั้ง banned words และ amount tiers
แก้ `user/settings.json` (ถ้ายังไม่มี copy จาก `user/settings.example.json` —
ตัว setup wizard สร้างให้อยู่แล้ว) ใส่เฉพาะค่าที่อยากเปลี่ยน:
```json
{
  "banned_words": ["คำที่ไม่อยากให้ขึ้น", "คำหยาบ"],
  "amount_tiers": {
    "show_message_min": 5000
  }
}
```
แล้ว: `docker compose restart backend`

### เปลี่ยนสี/ฟอนต์ overlay และ tip page
สร้าง/แก้ `user/web/theme.css` — โหลดทับ style เดิมทั้งสองหน้า แค่ refresh
browser source ใน OBS (อยากแก้ลึกกว่านั้น `app/overlay/style.css` / `app/tip/style.css`
ก็ยังแก้ได้ แต่จะไปชนกับการอัปเดตระบบ — theme.css ปลอดภัยกว่า)

### เปลี่ยนเสียง alert
วางไฟล์เสียงของคุณ (ฟอร์แมต WAV ชื่อ `alert.wav`) ที่ `user/web/sounds/alert.wav`
— ระบบใช้แทนเสียง default ทันที แค่ refresh browser source

### อัปเดตระบบเป็นเวอร์ชันใหม่
```bash
git pull                      # ดึงหน้าเว็บ/ไฟล์ config เวอร์ชันใหม่
docker compose pull           # ดึง backend image เวอร์ชันใหม่
docker compose up -d          # รีสตาร์ตด้วยของใหม่
```
ของใน `user/` (settings, theme, เสียง) อยู่ครบเหมือนเดิมทุกครั้ง

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
| QR ไม่ขึ้น | Secret key ผิด หรือ test/live mode ไม่ตรงกับ key | เช็ค key ใน dashboard ของ gateway (test key คู่กับ test mode เท่านั้น) |
| tip ไม่ขึ้น overlay หลังจ่าย | Webhook URL ผิดหรือ Cloudflare Tunnel ไม่ได้รัน | `docker compose ps` ดูว่า cloudflared up + เช็ค URL ใน dashboard gateway ว่าสะกดถูก |
| `[STARTUP ERROR]` | ค่าใน .env ยังเป็น placeholder หรือว่าง | เปิด .env เช็คทุกค่าว่าไม่มี CHANGEME — ข้อความ error บอกชื่อตัวที่ขาดตรงๆ |
| Overlay ไม่ขึ้นใน OBS | token ใน URL ไม่ตรงกับ OVERLAY_TOKEN ใน .env | เช็ค URL ของ browser source |
| Docker ไม่รัน / คำสั่งฟ้อง error | Docker Desktop ไม่ได้เปิด | เปิด Docker Desktop รอวาฬนิ่ง แล้วลองใหม่ |
| คำสั่งฟ้อง "no configuration file" | Terminal ไม่ได้อยู่ในโฟลเดอร์โปรเจกต์ | `cd` เข้าโฟลเดอร์ก่อน (หรือใช้ทริค address bar ในขั้น 4.2) |

### ติดปัญหาแก้ไม่ออก — ขอความช่วยเหลือยังไง

1. รันคำสั่งนี้แล้วคัดลอกผลลัพธ์ ~30 บรรทัดสุดท้าย:
   ```bash
   docker compose logs backend
   ```
2. เปิด issue ที่หน้า GitHub ของโปรเจกต์ → เล่าว่าทำขั้นไหนอยู่ เห็นอะไร + แปะ log
3. ⚠️ **ห้ามแปะไฟล์ `.env` หรือ key/secret/token ใดๆ ลงใน issue เด็ดขาด** — log จากคำสั่งข้อ 1 ปลอดภัย (ระบบออกแบบมาไม่พิมพ์ secret ลง log)

---

## คำถามที่เจอบ่อย (Q&A)

**Q: ต่างจาก TipMe ยังไง?**
TipMe หักค่าแพลตฟอร์ม 10% และถือเงินไว้รอจ่ายเป็นรอบ — ระบบนี้**หัก 0%** (เหลือแค่ค่า gateway ~1.65%) และเงินเข้าบัญชี Omise/Stripe ของคุณ**โดยตรงทันที** ไม่มีใครถือเงินแทน

**Q: คอมดับ / ลืมเปิดระบบ แล้วมีคนโอนมา เงินหายไหม?**
ไม่หาย — เงินอยู่ที่ gateway ตั้งแต่วินาทีที่เขาจ่าย ระบบนี้แค่ "โชว์ขึ้นจอ" พอเปิดระบบกลับมา มันไปเช็คกับ gateway เองว่าพลาดรายการไหนไปแล้วบันทึกให้ครบ (รายการเก่าเกิน ~10 นาทีจะไม่เด้งการ์ดซ้ำ กันการ์ดทะลักจอตอนเปิดเครื่อง — แต่ยอดบันทึกครบ)

**Q: มีคนจ่ายเงินมาเพื่อด่าหยาบๆ ขึ้นจอ ทำยังไง?**
สามชั้น: (1) เขาต้อง**จ่ายเงินจริง**ถึงส่งข้อความได้ — ป่วนมีต้นทุนทุกครั้ง (2) เพิ่มคำต้องห้ามใน `settings.json` → `banned_words` ระบบกรองให้ (3) ตั้ง `show_message_min` ให้ข้อความโชว์เฉพาะยอดที่สูงพอ และถ้าโดนจริง refund ผ่าน dashboard ของ gateway ได้ (ดูเงื่อนไขการคืนเงินในหมายเหตุด้านล่าง) — เขาเสียเงินฟรี

**Q: ขั้นต่ำ tip เท่าไหร่? ตั้งเองได้ไหม?**
ต่ำสุด **฿20** — เป็นเพดานของ gateway ลดต่ำกว่านี้ไม่ได้ ปรับ*ขึ้น*ได้ตามใจ

**Q: มีคนปลอมยอด tip ขึ้นจอได้ไหม?**
ไม่ได้ — ยอดที่ขึ้นจอมาจากใบยืนยันที่ gateway **เซ็นลายเซ็นดิจิทัล**มาเท่านั้น ของปลอมถูกระบบปฏิเสธอัตโนมัติ และระบบไม่เก็บเลขบัตร/บัญชีของใครเลย (gateway ถือข้อมูลการเงินทั้งหมด) สิ่งเดียวที่คุณต้องระวังคือไฟล์ `.env` — อย่าให้ติดจอตอน share screen

**Q: อยากเปลี่ยนสีการ์ด/เสียง/animation แต่เขียนโค้ดไม่เป็น?**
ของพื้นฐาน (คำต้องห้าม, ยอดขั้นต่ำโชว์ข้อความ, ไฟล์เสียง) แก้ `settings.json` ไม่ใช่โค้ด ส่วนหน้าตา (สี ฟอนต์ animation) ให้ AI ช่วยแก้ได้ — ระบบออกแบบเผื่อไว้แล้ว: โซนหน้าตาแก้พังยังไง ส่วนเงินไม่พังตาม ดูวิธีใน [VIBECODE.md](VIBECODE.md) แก้เสร็จรัน `make verify` เขียว = โอเค แดง = undo

**Q: มี TTS อ่านข้อความ / จ่ายด้วยบัตรได้ไหม?**
ยังทั้งคู่ — ตอนนี้ PromptPay + เสียง alert อย่างเดียว TTS กับบัตรอยู่ในแผนรุ่นถัดไป

**Q: ภาษีล่ะ?**
รายได้ tip เป็นรายได้ของคุณ ต้องยื่นเอง — ทุกรายการอยู่ใน dashboard ของ gateway ดึงรายงานไปประกอบการยื่นได้ ข้อแนะนำสำคัญ: **บัญชี gateway นี้ใช้กับ tip อย่างเดียว อย่าปนกับธุรกิจอื่น**

**Q: ถ้าพังกลางไลฟ์ ใครซ่อมให้?**
ตรงๆ: **ไม่มี support** — นี่คือระบบ fork-and-own คุณเป็นเจ้าของเครื่องตัวเอง สิ่งที่ระบบให้แทน: มัน restart ตัวเองเมื่อ crash, เงินไม่หายเพราะ gateway ถือ (ข้อแรกของ Q&A), และปัญหาที่พบบ่อยอยู่ในตาราง Troubleshooting ด้านบน ความเสี่ยงจริงต่ำกว่าที่กลัว: ต่อให้ overlay ดับทั้งไลฟ์ สิ่งที่เสียคือ "การ์ดไม่เด้ง" ไม่ใช่ "เงินหาย"

---

## หมายเหตุสำคัญ

- **ค่า gateway**: PromptPay ~**1.65%** ต่อยอด (Omise +VAT 7% ≈1.77%; Stripe ตามสถานะภาษีบัญชี + ฿10 ต่อการคืนเงิน) หักจากยอดที่ streamer ได้รับ — ระบบนี้ไม่หักเพิ่ม
- **เรื่องคืนเงิน**: PromptPay ผ่าน Omise คืนเงินไม่ได้; Stripe คืนได้แต่มีค่าธรรมเนียม ฿10 — ควรแจ้ง supporter ก่อนจ่าย
- **ความรับผิดชอบ**: KYC, ภาษี, และการปฏิบัติตามเงื่อนไขของ gateway เป็นของ streamer เอง — [Omise Terms](https://www.omise.co/th/terms) · [Stripe Terms](https://stripe.com/th/legal/ssa)
- **Security**: หากพบช่องโหว่ ดู `SECURITY.md` (repo root)
