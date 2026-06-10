# Quick Start — checklist 1 หน้า

ฉบับย่อของ [SETUP.md](SETUP.md) สำหรับกันหลงว่าอยู่ขั้นไหน — แต่ละข้อมีลิงก์กลับไป
อ่านละเอียด. ติดตั้งครั้งแรกใช้เวลารวม ~1–2 ชั่วโมง

**ต้องมีก่อนเริ่ม:** คอมที่ใช้สตรีม (Mac/Windows/Linux) · [Docker Desktop](https://www.docker.com/products/docker-desktop/) · OBS · โดเมน (~300–500฿/ปี — มีแนะนำวิธีซื้อใน SETUP)

## Checklist

- [ ] **1. Gateway** — สมัคร [Omise](SETUP.md#ขั้นตอนที่-1--ตั้งค่า-omise) (หรือ [Stripe](SETUP.md#ทางเลือก-ใช้-stripe-แทน-omise)) → ได้ **Secret key (test mode)** + สร้าง webhook ชี้ `https://tip.โดเมนคุณ/webhooks/omise` → ได้ **Webhook secret**
- [ ] **2. Cloudflare Tunnel** — [ตั้ง tunnel](SETUP.md#ขั้นตอนที่-2--ตั้งค่า-cloudflare-tunnel) ชี้โดเมนเข้าเครื่องคุณ (ไม่ต้องเปิด port) → ได้ **Tunnel token**
- [ ] **3. OBS** — [เปิด WebSocket Server](SETUP.md#ขั้นตอนที่-3--ตั้งค่า-obs-websocket) (Tools → WebSocket Server Settings) → จด **password**
- [ ] **4. ติดตั้งระบบ** — [ดาวน์โหลด](SETUP.md#41-ดาวน์โหลด-code) (ZIP หรือ `git clone`) แล้ว:
  - **Mac:** ดับเบิลคลิก `setup.command` — wizard ถามค่าจากข้อ 1–3 ทีละตัว แล้วเสนอรันระบบให้เลย
  - **Linux:** `make setup`
  - **Windows:** [กรอก `.env` เอง](SETUP.md#42-สร้างไฟล์-env) แล้ว `docker compose up -d`
- [ ] **5. OBS Browser Source** — เพิ่ม source URL `http://127.0.0.1:8080/?token=<OVERLAY_TOKEN>` (wizard print ให้ / ดูใน `.env`) ขนาด 1920×1080 — [รายละเอียด](SETUP.md#44-ตั้ง-obs-browser-source-หน้า-overlay)
- [ ] **6. ทดสอบด้วยเงินปลอม** — [Test 1–5](SETUP.md#ขั้นตอนที่-5--ทดสอบ-ทำครบก่อน-go-live): จ่าย test mode → การ์ดเด้งบน OBS ขณะ Start Streaming
- [ ] **7. เงินจริง** — KYC ผ่านแล้ว [สลับ key เป็น live](SETUP.md#ขั้นตอนที่-6--switch-เป็น-live-mode-เงินจริง) → ทดสอบจริง ฿20 หนึ่งครั้ง

## หลังติดตั้ง

| อยากทำ | ที่ไหน |
|---|---|
| ใช้งานประจำวัน / แก้ปัญหา | [SETUP.md — การใช้งานประจำวัน](SETUP.md#การใช้งานประจำวัน-หลังติดตั้งเสร็จ) |
| ตั้งคำต้องห้าม, ขั้นต่ำโชว์ข้อความ, สี, เสียง | โฟลเดอร์ `user/` — [SETUP.md — ปรับแต่ง](SETUP.md#ปรับแต่ง) |
| อัปเดตเวอร์ชันใหม่ | `git pull && docker compose pull && docker compose up -d` — ของใน `user/` ไม่หาย |
