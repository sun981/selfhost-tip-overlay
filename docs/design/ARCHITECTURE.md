# Architecture — Tip Overlay System (PoC)

เอกสารนี้ลงรายละเอียดสถาปัตยกรรมเชิงลึกของระบบเพื่อ review ก่อนเขียนโค้ด ครอบคลุม: tech stack + เหตุผล, โครงสร้างระบบ, data model, dataflow ทุกเส้น, security architecture, deployment topology, failure modes
อ้างอิงข้อบังคับจาก [`SPEC.md`](./SPEC.md) — เอกสารนี้ไม่ override ข้อบังคับด้านความปลอดภัย แต่ทำให้มันเป็นรูปธรรม

> สถานะ: **as-built (2026-06-10)** — PoC สร้างเสร็จ + ผ่าน pre-OSS audit แล้ว. decisions ใน §3 ถูก implement ครบ. §14 = คำถามจากรอบ review เดิม (ตอบครบแล้ว, LOCKED block ด้านบน supersede)

> [!warning] Wording — เปลี่ยน "Donate" → "Tip" (policy risk) %%review claude 2026-06-03%%
> เช็ค Omise [prohibited-businesses/thailand](https://docs.omise.co/prohibited-businesses/thailand) แล้ว:
> - **§1.3 Financial services (ห้าม):** _"Money transfer services, Cash gifting, **Donations** or Check Cashing"_ → คำว่า Donations อยู่ใน list ห้าม (กลุ่ม money-service-business). brand merchant ว่า "Donate" เสี่ยงโดนจัดเข้า bucket นี้ → **KYC reject / โดน suspend ภายหลัง**
> - **§1.5 Crowdfunding / Charitable / Fund-raising:** ห้ามเฉพาะ channel **TrueMoney / Alipay / WeChat** — **PromptPay + card ไม่โดน** → flow/ดีไซน์ PoC ไม่พัง, ความเสี่ยงอยู่ที่ระดับ merchant-description/KYC ล้วน
> - **"Tip" / "Support"** ไม่อยู่ใน list ห้ามเลย + ตรงความจริง (gratuity ให้ความบันเทิง = ขายบริการปกติ) → ความเสี่ยงต่ำกว่าชัด. TipMe (ตัวที่มาแทน) ก็ใช้คำ "Tip"
> - **สรุป: instinct ถูก — เปลี่ยนเป็น Tip.** เป็น **rename cascade** ไม่ใช่แค่ label: ชื่อโปรเจกต์ "Donation Overlay System", โฟลเดอร์ "Donation Selfhost", หน้า/ปุ่ม donate, claim "0% fee" §1, SPEC.md
> - เพิ่มเติม (recall ไม่ใช่ fetched-source — verify กับทนายเอง): ไทยมี **พ.ร.บ.ควบคุมการเรี่ยไร พ.ศ.2487** — solicit donation สาธารณะอาจต้องขออนุญาต; framing "Tip = ค่าตอบแทนบริการ" เลี่ยงประเด็นเรี่ยไรด้วย

> [!success] LOCKED — review round 2 (2026-06-03) — ข้อสรุปสุดท้าย ใช้สร้าง PoC (supersede §14 + note กระจัดกระจาย)
> **Naming:** product = **"Tip Overlay System"**. user-facing ทุกจุด (หน้า/ปุ่ม/README/ข้อความถึงผู้ให้/supporter) = **"Tip"** — ห้าม "Donate/Donation". **code identifier ทั้งหมดเปลี่ยนแล้ว** (`tips` table, `supporter_name`, `TipEvent`, `process_tip`) — โปรเจกต์เป็น open source ดังนั้น identifier ต้องสะอาดด้วย
> **PoC scope (ทำรอบนี้):** PromptPay server-side ไม่ใช้ Omise.js (D2) · SQLite (D5) · **min ฿20** (Omise hard limit, §14 Q2) · overlay **local** (localhost, OBS เครื่องเดียวกับ backend, ไม่ผ่าน tunnel — §14 Q3) · ingress **path-based** (`/`=tip page, `/webhooks/omise` — §14 Q5) · **word-filter** + **amount-tiers** (ปรับจาก `settings.json`) + **alert sound** (static) · feedback หลังจ่าย = มี · config = **`settings.json` + CSS theme เท่านั้น ไม่มี config UI** (user custom เองผ่านไฟล์ — §14 Q8) · 🔧[rev 2026-06-05] **gateway เลือกได้ `PAYMENT_GATEWAY=omise|stripe`** (ทั้งคู่ PromptPay server-side ไม่ใช้ client JS; Stripe = adapter ที่ 2 ใน Secure Core — §9.5)
> **Roadmap (ยังไม่ทำ):** card (+Omise.js+SRI) · TTS (provider=Google ตอน build) · **donor-pays-fee toggle** (§14 Q10) · goal bar / top-tipper · config UI (ออกแบบให้มี auth ตั้งแต่วันแรก) · moderation hold queue · remote OBS (seam พร้อมแล้ว §8.5) · homelab/LAN mode (overlay bind LAN + token; `OBS_WS_HOST` รองรับแล้ว)
> **Hosting scope 🔧[rev 2026-06-10]:** self-host บน **hardware ที่ user เป็นเจ้าของเท่านั้น** — เครื่องเดียวกับ OBS หรือ homelab ใน LAN เดียวกัน. **cloud VPS = ไม่ support** (threat model คนละชั้น: admin surface บน internet, secret บนเครื่องเช่า, ต้องมี auth เต็มรูปแบบ)
> **Defaults (ไม่ค้าน = ใช้เลย):** message cap 200 ตัว · privacy purge 90 วัน · recon ไม่ push ขึ้นจอถ้า `paid_at` เก่ากว่า ~10 นาทีก่อน startup (ยัง record เข้า DB)
> **Build handoff:** PoC จะสร้างโดย session ใหม่ (Sonnet + advisor) ที่**ไม่มี chat history นี้** → docs ต้องครบในตัว. ลำดับสร้าง = SPEC §10. ค้าง: rename folder (manual step ดู handoff)

---

## 1. Purpose & scope

ระบบรับ **tip** สำหรับ streamer แบบ self-host มาแทน TipMe (ปิดตัว) จุดขายเทียบ TipMe: (user-facing = "Tip"; internal identifier เช่น `tips`/`supporter` เก็บเดิม ดู LOCKED block บนสุด)

| | TipMe | ระบบนี้ |
|---|---|---|
| ค่าธรรมเนียม | หัก 10% (แพลตฟอร์ม) | **ระบบนี้หัก 0%** — มีแต่ค่า gateway ของ Omise: **PromptPay 1.65% + VAT 7%** (≈1.77%), card 3.65%+VAT |
| การถอนเงิน | รอสัปดาห์ที่ 2 ของเดือนถัดไป | **settle ตรงผ่าน Omise** ไม่มีตัวกลางถือเงิน |
| โค้ด | ปิด | **open source (MIT)** ตรวจสอบได้ |
| ปรับแต่ง | ไม่ได้ | self-host ปรับเองได้เต็มที่ |

> ⚠️ อย่าเคลม "ฟรี/0%" ลอยๆ — ระบบ**ไม่หักค่าคอม** แต่ donor/streamer ยังจ่ายค่า gateway ของ Omise (PromptPay 1.65%+VAT) README ต้องระบุชัดว่าใครรับภาระ fee (default = หักจากยอดที่ streamer ได้รับ)

**Scope ของ PoC นี้**: PromptPay เท่านั้น, เครื่องเดียว, docker-compose, พิสูจน์ว่า "จ่าย → verify → ขึ้น overlay → เงินไม่หาย" ทำงานจริงและปลอดภัย
**ไม่อยู่ใน PoC** (ดู §15 Roadmap): card, tip goal, top tipper, TTS, alert image, donor-pays-fee toggle, multi-streamer  (🔧[rev] **เข้า PoC แล้ว**: word-filter, amount-tiers, alert sound)

### 1.1 Distribution model — fork-and-own (ไม่ maintain ส่วนกลาง)
- **ปล่อย OSS, ไม่เก็บเงิน, ไม่ commit ว่าจะ maintain** — แต่ละ deploy เป็น instance ของ streamer เองอยู่แล้ว (ไม่มี service กลาง) → fork-and-own เข้ากับ self-host โดยธรรมชาติ ผู้สร้างเป็น "originator" ไม่ใช่ "maintainer"
- ⚠️ **payment/security tool ที่ไม่ maintain อันตรายกว่า static tool**: CVE ใน dep, Omise API drift, pinned digest ช่วย reproducibility/audit แต่ก็ **freeze dep ไว้ที่เวอร์ชันที่วันหน้าอาจมีช่องโหว่**
- ทางแก้ ≠ "ต้อง maintain" แต่ = **ทำให้ self-patch ถูกๆ**: `make verify` (§13) คือ **กลไกส่งมอบ** — forker (หรือ AI ของเขา) bump dep / ปรับตาม Omise → รัน `make verify` เขียว = ปลอดภัยพอจะ deploy. `SECURITY.md` ใส่ **freshness signal**: "deps pinned ณ DATE, last review DATE, bump + verify ก่อนเชื่อ"
- **อย่าเคลมว่า maintained** — เคลมแค่ "reference implementation, คุณเป็นเจ้าของความปลอดภัยของ fork คุณเอง"

### 1.2 Template ambition — รับยุค personal-tools (วาง ไม่ build framework)
- มองยาว: หลังยุค AI คนจะ vibecode personal tool กันมากขึ้น → ของที่มีค่าจริงระยะยาวอาจเป็น **skeleton ของ "self-host tool ที่ vibecode ได้ + ปลอดภัย"** (core/edge split, hook, AGENTS.md, config-over-code, make verify) ไม่ใช่ตัว logic tip
- **tip = ตัวพิสูจน์ pattern** — สร้าง instance จริง 1 ตัวให้ดีก่อน, pattern จะโผล่เป็น template ที่ documented. **extract เป็น skeleton ทีหลัง** เมื่อพิสูจน์แล้ว — **ห้าม build generic framework ตอนนี้** (Karpathy / SPEC "ห้าม over-engineer")

---

## 2. Design principles

1. **ระบบไม่ถือเงิน (never-custody)** — donor → Omise → บัญชี streamer โดยตรง นี่คือ trust claim หลักที่ตรวจสอบได้ของ OSS
2. **Single-tenant blast radius** — skey อยู่บนเครื่อง streamer คนเดียว ถ้าถูก compromise กระทบเฉพาะบัญชี Omise ของ streamer คนนั้น ไม่ลามคนอื่น (ข้อได้เปรียบด้านความปลอดภัยเหนือ SaaS รวมศูนย์). 🔧[rev 2026-06-03 — ซื่อสัตย์ P1#6] skey เป็น **live key ที่ refund ได้ + อ่าน transaction ทั้งบัญชี** → RCE = กระทบ**ทั้งบัญชี Omise** ของ streamer ไม่ใช่แค่ tip แอปนี้ (mitigate ด้วย container hardening §10.1). **assumption: บัญชี Omise นั้นใช้กับ tip อย่างเดียว — อย่าเอาบัญชีที่ทำธุรกิจอื่นมาปน**
3. **Idempotency = ตัวการันตีความถูกต้อง** ไม่ใช่ cursor — ประมวลผล charge เดิมซ้ำได้ปลอดภัยเสมอ
4. **ห้าม over-engineer** — สร้าง PromptPay แบบ concrete ทำ card เป็น extension point อย่า abstract ล่วงหน้า
5. **Secure by default** — ขาด secret = refuse start, CORS explicit, ทุก output escape
6. **Vibecode-safe by structure** — user เป็น streamer ไม่ใช่ coder จะใช้ AI แก้/ต่อยอด → ความปลอดภัยต้องมาจาก**โครงสร้าง** ไม่ใช่วินัยคนเขียน. แยก Secure Core (ห้ามแตะ) ออกจาก Safe Edge (vibecode สบาย) — ดู §13

---

## 3. Decisions (locked — veto ได้)

| #   | ประเด็น               | ตัดสินใจ                                                                                | เหตุผล                                                                                   |
| --- | --------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| D1  | สร้าง charge          | **`POST /charge` ฝั่ง server (skey)**                                                   | pkey สร้าง charge ไม่ได้ สร้างได้แค่ source/token — server เท่านั้นที่ charge ได้        |
| D2  | **PromptPay flow** ⚠️ | **สร้าง source + charge ฝั่ง server ทั้งหมด → tip page ไม่โหลด Omise.js เลย**        | ดู §3.1 — กระทบ frontend + ทำให้ §4.7.4 (SRI) ไม่ applicable กับ PoC                     |
| D3  | donor name/message    | round-trip ผ่าน `charge.metadata`                                                       | ตรงตาม SPEC §4.4 + reconciliation ดึงกลับได้                                             |
| D4  | push                  | **SSE** (ไม่ใช่ WebSocket)                                                              | one-way server→overlay, auto-reconnect, plain HTTP, ผ่าน tunnel ง่าย                     |
| D5  | DB                    | **SQLite** (schema portable ไป Postgres)                                                | self-host ชิ้นส่วนน้อยสุด, SPEC §8 อนุญาต                                                |
| D6  | frontend              | **vanilla static** (ไม่มี build step)                                                   | audit ง่าย, ไม่ต้องมี node toolchain ตอน deploy                                          |
| D7  | live re-check         | เช็คเฉพาะตอน `POST /charge` **ไม่เช็คตอน webhook**                                      | ดู §3.2 — กฎสำคัญ                                                                        |
| D8  | license               | **MIT** + DISCLAIMER                                                                    | ผู้ deploy รับผิดชอบ KYC/ภาษี/เงื่อนไข Omise เอง                                         |
| D9  | domain                | streamer ลงทะเบียน domain เองบน Cloudflare                                              | self-host เลี่ยงไม่ได้ เป็น flexibility ที่ยอมรับ                                        |
| D10 | QR                    | **backend proxy รูป QR มา serve เอง**                                                   | CSP `img-src 'self'`, ไม่พึ่ง Omise CDN ตอนแสดง, audit สะอาด (alt: `<img>` ตรงจาก Omise) |
| D11 | extensibility         | **processing pipeline 1 จุด (seam) ระหว่าง verified→push** ไม่ใช่ plugin framework      | รองรับ word filter / TTS / moderation ทีหลังโดยไม่แตะ flow หลัก — ดู §12                 |
| D12 | vibecode safety       | **แยก code เป็น Secure Core / Safe Edge + customization ผ่าน config ก่อนเสมอ**          | user vibecode ด้วย AI → กันพังโดยไม่ตั้งใจด้วยโครงสร้าง ไม่ใช่วินัย — ดู §13             |
| D13 | core isolation        | **PreToolUse hook block การแก้ core (force ถาม user แม้ automode) — build ขั้นสุดท้าย** | enforcement ชั้น tool แข็งกว่า AGENTS.md; ทำก่อนจะ block การ build เอง — ดู §13.5        |
| D14 | gateway flex          | **`PaymentGateway` adapter interface (Omise concrete)** — เพิ่มเจ้า = adapter ใน Secure Core + review ไม่ใช่ config | verify ต่างเจ้า + security-critical → reviewed-flex ไม่ใช่ vibecode toggle — ดู §9.5      |
| D15 | DB/hosting flex       | **DB = `DATABASE_URL` config (SQLAlchemy), hosting = compose portable**                | config-flex ล้วน zero-code — แต่มี caveat OBS/NAS/cloud — ดู §10.3                       |
| D16 🔧[rev 2026-06-10] | user customization | **`user/` dir แยก physical** — settings override + theme.css + เสียง อยู่นอก upstream tree (gitignored, bind-mount) | update (`git pull`/`compose pull`) ไม่มีทางชน customization — แก้ปัญหา fork-drift ที่ระดับโครงสร้าง ไม่ใช่ docs |
| D17 🔧[rev 2026-06-10] | distribution | **prebuilt backend image บน ghcr** publish โดย CI ทุก release tag (`vX.Y.Z` → `X.Y.Z`+`X.Y`, ไม่มี `latest`), gated หลัง verify; compose มี `image:`+`build:` คู่กัน | user ไม่ technical update ด้วย `compose pull` ไม่ต้องมี git/toolchain; fork ยัง build เองได้ |
| D18 🔧[rev 2026-06-10] | schema evolution | **forward-only migration runner + `schema_version`** ใน core/db, รันตอน startup, fail-closed, backup SQLite ก่อน migrate, DB ใหม่กว่า build = refuse start | สร้างก่อนมี schema change จริง — ทำทีหลังตอน user มีข้อมูลจริงแพงกว่ามาก |

### 3.1 ⚠️ D2 ขยายความ — ทำไม PoC ไม่ใช้ Omise.js (จุดที่อยากให้ review มากสุด)

PromptPay **ไม่มีข้อมูลบัตร** (ไม่มี PAN) → ไม่มีประเด็น PCI → Omise รองรับการสร้าง source + charge ในคำขอเดียวฝั่ง server ด้วย skey ([Omise PromptPay docs](https://docs.omise.co/promptpay))

ผลที่ตามมา:
- tip page **ไม่โหลด JS ของบุคคลที่สาม** → audit ง่ายขึ้น, attack surface เล็กลง
- **SPEC §4 / §7.4 "Omise.js pinned + SRI" → ไม่ applicable กับ PoC นี้** (เพราะไม่มี Omise.js) — นี่ไม่ใช่การข้าม non-negotiable แต่เป็นการ "ไม่มีของที่ต้อง pin" ข้อบังคับนี้ **กลับมา when card support lands** (card บังคับ tokenize ฝั่ง client ด้วย Omise.js เพราะ PAN ห้ามแตะ server ของเรา)
- **QR มาจากไหน?** QR เกิดตอน backend สร้าง charge ฝั่ง server — Omise คืน `charge.source.scannable_code.image.download_uri` (PNG โฮสต์ที่ Omise) ไม่เกี่ยวกับ Omise.js (Omise.js มีไว้ tokenize บัตรเท่านั้น) → ตัด Omise.js ไม่กระทบ QR
- QR ถึง donor 2 ทาง: (a) `<img src=download_uri>` ตรงจาก Omise (CSP img-src ต้อง allow Omise host) หรือ **(b) backend proxy รูปมา serve เอง → CSP `img-src 'self'`** (D10, แนะนำ)

> ถ้าต้องการให้ PoC มี card ตั้งแต่แรก จะกลับไปใช้ Omise.js + SRI ทันที — บอกได้

### 3.2 ⚠️ D7 ขยายความ — live gate วางตรงไหน

- **`POST /charge`**: เช็ค live ก่อน ถ้าไม่ live → ปฏิเสธ (บังคับ UX gate ฝั่ง server กัน client หลบ JS)
- **`POST /webhooks/omise`**: **ห้ามผูกกับ live status เด็ดขาด** — เงินจ่ายไปแล้ว, PromptPay จ่ายแบบ async (donor อาจจ่ายช้าหลัง stream จบ) ถ้าปฏิเสธเพราะไม่ live = tip หาย **webhook ต้องบันทึกเสมอ ไม่ว่าจะ live หรือไม่**

---

## 4. Tech stack

| ชั้น | เลือก | เวอร์ชัน/หมายเหตุ |
|---|---|---|
| Backend | Python + FastAPI + uvicorn | async, SSE ง่าย, pin ใน lock file |
| HTTP client (Omise API) | `httpx` | สร้าง charge, reconciliation list |
| OBS link | `obs-websocket` v5 (OBS 28+) client (`simpleobsws` หรือ raw) | `GetStreamStatus.outputActive`, มี password |
| DB | SQLite (PoC) → schema portable Postgres | ผ่าน SQLAlchemy Core/ORM เพื่อย้ายง่าย — 🔧[rev P2#9] `PRAGMA journal_mode=WAL` + `busy_timeout`; write (webhook+recon) serialize ผ่าน single conn/lock, SSE = read ไม่ชน |
| Migration | Alembic (หรือ schema.sql ตรงๆ สำหรับ PoC) | |
| Frontend / overlay | vanilla HTML/CSS/JS, static | ไม่มี build step |
| Static server | nginx (alpine, pinned digest) | ตั้ง CSP header ต่อหน้าได้ |
| Tunnel | cloudflared | outbound only |
| Container | docker-compose, base image pin ด้วย digest | SPEC §4.9 |

---

## 5. System structure

```
                              Internet (donor browser)
                                       │
                                       │ HTTPS (Cloudflare edge, SSL Full + HSTS)
                                       ▼
                          ┌────────────────────────┐
                          │   Cloudflare Tunnel     │  outbound only, ไม่เปิด inbound port
                          │      (cloudflared)      │
                          └───────────┬─────────────┘
                                      │ ingress rules (hostname/path → service)
        ┌──────────────────┬─────────┴──────────┬──────────────────┐
        ▼                  ▼                     ▼                  ▼
  tip page         overlay page          /api/* , /webhooks/*   (live-status = /api/live-status)
  (nginx static)      (nginx static)         backend (FastAPI)
        │                  ▲                     │   │
        │ fetch /api/*     │ SSE /api/events     │   │
        └──────────────────┼─────────────────────┘   │
                           │ push (verified successful)│
                           └────────────────────────────┘
                                      │
                          ┌───────────┴───────────┐
                          ▼                       ▼
                    SQLite (volume)        OBS WebSocket
                    tips, host.docker.internal:4455
                    recon_state            (host-only, ห้าม expose)
                                                 │
                                          Omise API (httpx, outbound)
                                          create charge / list (reconciliation)
```

### 5.1 Services (docker-compose)

| service | หน้าที่ | network exposure |
|---|---|---|
| `backend` | API, webhook verify, charge create, reconciliation, SSE, OBS client, ถือ skey/webhook secret | ผ่าน tunnel เฉพาะ path `/api/*` + `/webhooks/*` |
| `frontend` | tip page (static, nginx) | public ผ่าน tunnel |
| `overlay` | overlay page (static, nginx, CSP เข้ม) | 🔧[rev 2026-06-03] **local เท่านั้น** (OBS browser source เครื่องเดียวกับ backend → localhost, **ไม่ผ่าน tunnel**). token ยังมี (default-deny). remote OBS = เปิด tunnel+token เอง(config, สาย tech §8.5) |
| `db` | SQLite ผ่าน volume (PoC) — service จริงจะมีเมื่อย้าย Postgres | internal เท่านั้น |
| `cloudflared` | tunnel | outbound only |

> หมายเหตุ: PoC ใช้ SQLite ผ่าน volume mount ที่ backend (ไม่ต้องมี db service แยกก็ได้) — service ที่ 5 จะกลายเป็น postgres เมื่อย้าย ตอนนี้นับ cloudflared เป็นชิ้นที่ 5 ตาม SPEC §7.1

### 5.2 ส่วนที่ public vs internal

- **Public ผ่าน tunnel** (path-based, 🔧[rev]): tip page (`/`), `GET /api/live-status`, `POST /api/charge`, `GET /api/charge/{id}/status`, `POST /webhooks/omise`
- **Local/host-only เท่านั้น** (🔧[rev] overlay ย้ายมาที่นี่): **overlay page + `GET /api/events/overlay`** (OBS ต่อ localhost ไม่ผ่าน tunnel), OBS WebSocket 4455, DB, skey, webhook secret
- `/api/live-status` คืนแค่ `{live: bool}` — เปิด public ได้เพราะ tip page (รันใน browser) ต้องเรียก

---

## 6. Data model

```sql
-- tip 1 แถวต่อ 1 charge — charge_id เป็น idempotency key
CREATE TABLE tips (
    charge_id     TEXT PRIMARY KEY,           -- Omise charge id (chrg_...) — unique กัน replay/ส่งซ้ำ
    status        TEXT NOT NULL,              -- pending | successful | failed | expired
    amount        INTEGER NOT NULL,           -- satang (1 THB = 100) เก็บตามที่ Omise ส่ง
    currency      TEXT NOT NULL DEFAULT 'thb',
    supporter_name TEXT,                       -- จาก metadata (escape ตอน render เสมอ)
    message       TEXT,                        -- จาก metadata (escape ตอน render เสมอ)
    source_type   TEXT,                        -- 'promptpay'
    created_at    TIMESTAMP NOT NULL,          -- ตอนเราสร้าง charge
    paid_at       TIMESTAMP,                   -- ตอน status -> successful
    pushed_at     TIMESTAMP,                   -- ตอน push ขึ้น overlay สำเร็จ (กัน push ซ้ำ)
    event_seq     INTEGER                      -- 🔧[rev 2026-06-03] monotonic seq เซ็ตตอน push → SSE `id:` สำหรับ Last-Event-ID replay (P0#2, §8.5)
);
CREATE INDEX IF NOT EXISTS idx_event_seq ON tips(event_seq);  -- 🔧[rev] overlay reconnect replay (P0#2)

-- bound ว่า reconciliation ย้อนหลังแค่ไหน (ไม่ใช่ correctness — idempotency เป็นตัวการันตี)
CREATE TABLE recon_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),  -- single row
    last_scan_at  TIMESTAMP
);
```

**Idempotency = แยก 2 เรื่องออกจากกัน** (record เงิน ≠ push overlay) — กันบั๊ก orphaned-push:
- `POST /charge` → `INSERT` แถว status=`pending`
- **record (เงิน)**: webhook/reconciliation เจอ successful → `UPDATE SET status='successful', paid_at=... WHERE charge_id=? AND status!='successful'` → idempotent บันทึกเงิน
- **push (overlay) — retry key คนละตัว**: push ทุกแถวที่ `status='successful' AND pushed_at IS NULL` → push สำเร็จค่อย set `pushed_at` → push ครั้งเดียว/charge

> ⚠️ **ห้ามใช้ status flip เป็น retry key ของ push**: ถ้า edge stage (§12) throw *หลัง* flip status แล้ว, status เป็น successful แล้ว → reconciliation รอบหน้า rowcount=0 → **ไม่ re-push** → เงินบันทึกแต่ไม่ขึ้นจอเงียบๆ. แยก `pushed_at IS NULL` เป็น key ทำให้ reconciliation re-push ของที่ค้างได้เสมอ

> ค่าเงินทั้งหมดเก็บเป็น **satang** หารด้วย 100 เฉพาะตอนแสดงผล (กันบั๊ก ฿100,000 vs ฿1,000) %%🔧[rev] ลบบรรทัดซ้ำ P2#8%%

---

## 7. Endpoints

| method | path | หน้าที่ | auth |
|---|---|---|---|
| GET | `/api/live-status` | `{live: bool}` จาก OBS | public |
| POST | `/api/charge` | สร้าง source+charge (skey), เขียน metadata, คืน QR | public + **live gate** + validation |
| GET | `/api/charge/{id}/status` | อ่าน status จาก **DB local** (ไม่ยิง Omise ทุก poll) — 🔧[rev] คืนแค่ `{status}` (+amount) **ไม่คืน name/message** กันใครรู้ charge_id อ่านข้อความ donor (P1#5) + rate-limit poll | public (รู้ id เท่านั้น) |
| GET | `/api/charge/{id}/qr` | 🔧[as-built] **QR proxy ตาม D10** — backend ดึงรูปจาก gateway มา serve เอง → overlay/tip page CSP `img-src 'self'` | public (รู้ id เท่านั้น) |
| GET | `/api/events/overlay?token=` | SSE stream tip ที่ verified แล้ว — 🔧[rev] emit `id: {event_seq}`; on reconnect อ่าน `Last-Event-ID` → replay เฉพาะ seq ใหม่กว่า (LIMIT N), fresh source (ไม่มี header) = start live ไม่ replay (P0#2) | **token** |
| GET | `/api/tips/recent?after={seq}` | 🔧[rev] backfill gap แบบ manual (overlay/bot ดึงย้อนหลัง), token-gated, return เฉพาะ field overlay ใช้ (P0#2) | **token** |
| POST | `/api/tips/{id}/replay` | 🔧[as-built] manual re-push tip เดิมขึ้น overlay (streamer สั่งฉายซ้ำ) — ไม่แตะ money record | **token** |
| POST | `/webhooks/omise`, `/webhooks/stripe` | verify sig → record → push — route ตาม `PAYMENT_GATEWAY` (§9.5); adapter ของ gateway ที่ไม่ได้เลือก = ไม่ mount | signature เท่านั้น (ไม่พึ่ง CORS) |
| GET | `/health` | 🔧[as-built] liveness สำหรับ compose healthcheck — ไม่คืนข้อมูล tip/secret | public |
| POST | `/api/dev/test-tip` | 🔧[as-built] **dev-only** ยิง test alert ผ่าน pipeline จริง (process_tip + SSE) **ข้าม payment/signature/DB** — mount เฉพาะ env `DEV_TEST_TRIGGER=1` (default ปิด → 404 ใน prod) | **token** (OVERLAY_TOKEN) + env flag |
| GET | `/` (tip), `/overlay` | static pages | overlay ต้องมี token |

**Validation ที่ `POST /charge`** (ก่อนสร้าง charge / เขียน metadata):
- `amount`: integer, อยู่ในช่วง min–max (เช่น 2000–10000000 satang = ฿20–฿100,000), `currency` บังคับ `thb`
- `donor_name`: ยาว ≤ N, charset จำกัด
- `message`: ยาว ≤ N (เช่น 200), charset จำกัด — **cap ตรงนี้ผูกกับ SPEC §4.5** (จำกัดก่อนเข้า metadata)
- live ต้อง = true ไม่งั้น 403

---

## 8. Dataflows

### 8.1 Live status
```
tip page (onload) ─GET /api/live-status─▶ backend ─obs-ws GetStreamStatus─▶ OBS
                                              outputActive ──────────────────────┘
   live=false → แสดง "ยังไม่ได้ไลฟ์" ไม่ render form
   live=true  → render form (amount/name/message)
```
backend cache ผล OBS สั้นๆ (เช่น 2–3s) กันยิง OBS ถี่เกิน

### 8.2 Charge creation (PromptPay) — ⚠️ ลำดับสำคัญ
```
1. donor กรอก amount + name + message บน tip page
2. tip page ─POST /api/charge {amount,name,message}─▶ backend
3. backend: เช็ค live (ไม่ live→403) + validate amount/name/message
4. backend ─create source(promptpay)+charge(skey), metadata={name,message}─▶ Omise API
5. backend INSERT tips(charge_id, status='pending', amount, name, message, ...)
6. backend คืน {charge_id, qr_download_uri, status:'pending'}
7. tip page แสดง QR + เริ่ม poll GET /api/charge/{id}/status ทุก ~2-3s
```
> **name/message ต้องเก็บ "ก่อน" สร้าง charge** เพราะมันถูกเขียนเป็น `charge.metadata` ตอนสร้าง — นี่คือสิ่งที่ทำให้ metadata round-trip (D3) ทำงานได้

### 8.3 Webhook receive (ด่านหลัก — SPEC §4.1–4.4)
```
Omise ─POST /webhooks/omise (raw body + Omise-Signature + Omise-Signature-Timestamp)─▶ backend
  a. อ่าน RAW body (ห้าม parse แล้ว stringify กลับ)
  b. signed = "<timestamp>" + "." + raw_body(utf-8)
  c. key = base64_decode(webhook_secret)
  d. expected = hex( HMAC-SHA256(key, signed) )
  e. Omise-Signature อาจมีหลายตัวคั่น comma (rotation 24ชม.) → loop เทียบทุกตัวด้วย hmac.compare_digest
       ไม่ตรงเลย → 401
  f. |now - timestamp| > 5 นาที → ปฏิเสธ (replay protection)
  g. parse event: ต้องเป็น key=='charge.complete', data.object=='charge'
  h. ถ้า charge.status == 'successful':
        [record] UPDATE SET status='successful', paid_at=... WHERE charge_id=? AND status!='successful'  ← commit เงินก่อน เสมอ
        [push]   ถ้า pushed_at IS NULL:
                    try: ev = process_tip(event) [seam §12, มี timeout]
                         ถ้าไม่ถูก DROP/HOLD → push SSE(ev) → set pushed_at
                    except/timeout: push **base tip** = amount+name แต่ 🔧[rev] **ตัด message เป็นว่าง/"[ซ่อน]"** (ไม่ push raw — กัน word-filter crash แล้วคำหยาบหลุด P0#3) → set pushed_at  ← edge พังไม่ทำให้ tip หาย/ไม่หลุดคำ
     ถ้า failed/expired → update status, ไม่ push
  i. ตอบ 200 (แม้เป็น duplicate ที่ verify ผ่าน) กัน Omise retry; 401 เฉพาะ sig ผิด
```
> ค่า amount/name/message ที่เอาไปแสดง = จาก **charge object ที่ verified นี้เท่านั้น** (SPEC §4.4) ไม่เอาจาก client
> **ไม่มีการเช็ค live ที่นี่** (D7)

### 8.4 Reconciliation (startup — idempotent re-scan, SPEC §6)
```
on backend start:
  1. lookback = recon_state.last_scan_at - buffer (เช่น -1 ชม.) หรือ default window ถ้าว่าง
  2. ─GET Omise charges list (created >= lookback, paginate)─▶ Omise
  3. แต่ละ charge ที่ status=='successful':
       ป้อนเข้า pipeline เดียวกับ 8.3.h: record (status) + push **เฉพาะแถว pushed_at IS NULL** — 🔧[rev P2#10] **`ORDER BY paid_at`**; ของเก่ามาก (paid_at ก่อน startup เกิน threshold) = **record + mark pushed เงียบๆ ไม่ push ขึ้นจอ** (อยู่ใน history/top-tipper ได้ แต่กัน burst ของเก่าทะลักจอตอน restart)
       → re-push ของที่ค้าง (handler เคยตายกลางทาง) ได้, ของที่ push แล้วไม่ซ้ำ
  4. set recon_state.last_scan_at = now
```
> cursor แค่ **bound ว่าย้อนหลังแค่ไหน** ไม่ใช่กลไกความถูกต้อง — idempotency คือกลไกความถูกต้อง ดังนั้นไม่ต้องแม่นระดับ paid-time (list API order by created ก็พอ)
> ⚠️ **assumption ที่ buffer พึ่งอยู่**: query ด้วย `created >= lookback` → charge ที่*สร้าง*ก่อน window แต่เพิ่ง*จ่าย*ระหว่าง downtime จะหลุด scan ได้ ถ้า QR มีอายุยาวกว่า buffer. ปลอดภัยเพราะ PromptPay QR expire เร็วกว่า buffer 1 ชม. — **ถ้าใครปรับ QR expiry ยาวขึ้น ต้องขยาย buffer ตาม** (buffer ≥ QR expiry เสมอ)
> เหตุผล: Omise ไม่การันตี retry webhook → fallback นี้กัน tip หายตอนเครื่องดับ

### 8.5 Overlay render (SPEC §4.5)
```
overlay page (OBS browser source) ─GET /api/events/overlay?token=─▶ SSE stream
  on event {name, message, amount}:
     - render ด้วย textContent (ไม่ใช่ innerHTML)
     - หาร amount/100 แสดงเป็น ฿
     - CSP เข้ม: default-src 'none'; script-src 'self'; connect-src 'self'; img-src 'self' data:
```
- 🔧[rev 2026-06-03] **overlay reconnect = ใช้ SSE `Last-Event-ID` ของฟรี** (ยืนยัน [MDN/WHATWG](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)): backend emit `id: {event_seq}` ทุก event → browser reconnect ส่ง header `Last-Event-ID` เอง → backend replay `WHERE event_seq > :last AND pushed_at NOT NULL ORDER BY event_seq LIMIT N` (token-gated) แล้วต่อ live. **fresh OBS source (ไม่มี Last-Event-ID) = start live ไม่ replay** (กันของเก่าทะลักจอ); retry default 3s ตั้ง `retry:` ได้. แทนระบบ "ack" ที่ลอย — ไม่ต้องประดิษฐ์เอง (P0#2)

---

## 9. Security architecture (map SPEC §4 → ส่วนของระบบ)

| SPEC | ทำที่ไหน |
|---|---|
| §4.1 signature verify | `POST /webhooks/omise` — raw body, base64-decode secret, HMAC-SHA256 hex, loop comma sigs, `hmac.compare_digest`, 401 ถ้าไม่ตรง — 🔧[rev] ✅ ยืนยันตรง [Omise api-webhooks](https://docs.omise.co/api-webhooks): signed = `<TIMESTAMP>.<RAW_BODY>`. **self-test (§13.2) ต้องใช้ test vector จริงจาก Omise doc ไม่ใช่ vector มั่ว** |
| §4.2 replay window | เทียบ `Omise-Signature-Timestamp` กับ now ±5 นาที |
| §4.3 idempotency | `charge_id` PK + guarded update (§6) |
| §4.4 ไม่เชื่อ client เรื่องเงิน | amount แสดงผล = จาก verified charge; name/message = donor เป็นเจ้าของข้อความ → ป้องกันด้วย escape (§4.5) ไม่ใช่ "verify" — ดู §9.1 |
| §4.5 XSS | overlay textContent + CSP เข้ม + cap length/charset ที่ `POST /charge` |
| §4.6 secret | env + `env_file`, startup refuse ถ้าขาด/placeholder, chmod 600 .env, ไม่ COPY/ARG เข้า image |
| §4.7 CORS | `Access-Control-Allow-Origin` = domain streamer จาก env (explicit ห้าม `*`); webhook ไม่พึ่ง CORS |
| §4.7.4 SRI | **ไม่ applicable กับ PoC** (ไม่มี Omise.js, D2) — กลับมาเมื่อมี card |
| §4.8 network/cert | Cloudflare Tunnel outbound only, SSL Full + HSTS (manual step ใน guide) |
| §4.9 อื่นๆ | ไม่ log secret/charge เต็ม, debug off, rate limit, pin deps + image digest |
| 🔧[rev] §4.9 rate-limit key (P0#1) | หลัง Cloudflare Tunnel socket-IP = Cloudflare ทุก req → **key ด้วย `CF-Connecting-IP`** (token-bucket/IP, in-mem พอ instance เดียว). header หาย = reject (ไม่ได้มาทาง tunnel). **trust ได้เพราะ Tunnel ไม่เปิด origin port (§10.1) → ทางเข้าเดียวคือผ่าน Cloudflare** — ไม่ใช่เพราะ IP-allowlist. + Cloudflare WAF rate-rule ชั้น edge. ([CF docs](https://developers.cloudflare.com/fundamentals/reference/http-headers/)) |

### 9.1 §4.4 — แยก trust model ให้ชัด (จุดที่ SPEC กำกวม)
- **amount = เงินจริง** → ต้องเท่ากับ charge object ที่ verify ด้วยลายเซ็นแล้ว ห้ามเชื่อค่าจาก client ตอนแสดงผล
- **name/message = ข้อความที่ donor เป็นเจ้าของเอง** → "ห้ามเชื่อ client" ไม่ใช่ frame ที่ถูก เพราะ donor *คือ* แหล่งข้อมูล สิ่งที่ต้องทำคือ **escape** (§4.5) + เก็บผ่าน `charge.metadata` (D3) เพื่อให้ webhook อ่านกลับมาได้ + ดึงคืนได้ตอน reconciliation
- ข้อความ unpaid (charge ยัง pending/failed) **ไม่มีวันถึง overlay** เพราะ push เฉพาะตอน verified `successful` (status filter ป้องกันให้)

### 9.2 Trust boundaries
- **เชื่อ**: Omise (ผ่านลายเซ็น), OBS (host-only), env secret
- **ไม่เชื่อ**: donor browser, request body ที่ webhook ก่อน verify, ข้อความ donor (escape เสมอ)
- **crown jewel**: skey + webhook secret — อยู่ใน backend เท่านั้น ไม่โผล่ frontend/overlay/log

### 9.3 Donor privacy & data retention
แยก 2 ชั้นให้ชัด:
- **Financial PII** (เลขบัตร/บัญชีธนาคาร/ตัวตนผู้จ่าย) → **เราไม่เห็น/ไม่เก็บเลย Omise เป็น system of record** (ผลพลอยได้จาก never-custody + D2) — claim privacy ที่แข็งสุด
- **alias + message** ที่ donor พิมพ์บนฟอร์ม → donor ตั้งใจให้ขึ้นจอ (public by intent) ไม่ใช่ตัวตนจริง **ต้อง persist** (overlay + top-tipper + reconciliation อ่านกลับ) → จัดการด้วย:
  - **retention config**: auto-purge หลัง N วัน (default เช่น 90 วัน) + endpoint/CLI ลบเองได้
  - ไม่ log ข้อความ donor ที่ระดับปกติ (ดู §9.4)
- ⚠️ tension: ถ้าอยาก max privacy (ไม่ persist message เลย) จะ**ทำ top-tipper/history/bot ไม่ได้** — เป็น decision (open Q)

### 9.4 Logging policy (เป็น security เพราะ log รั่ว = ช่องโหว่)
| Log ได้ | **ห้าม log เด็ดขาด** |
|---|---|
| event type, `charge_id`, status, amount, timing, error code | secret/skey/webhook secret ทุกชนิด |
| webhook verify pass/fail (ไม่ใส่ payload) | raw body / charge object เต็ม |
| reconciliation summary (กี่รายการ) | alias/message ของ donor (ระดับ info) |
| | stack trace ส่งไป client (เก็บ server-side เท่านั้น) |
- structured log → stdout (`docker logs`), debug off ใน prod (SPEC §4.9)
- redaction เป็นหน้าที่ของ **Secure Core** (อยู่ในโซนห้าม vibecode §13) — กัน AI เผลอ log เต็ม

### 9.5 Payment gateway adapter — reviewed-flex (ไม่ใช่ config) (D14)
gateway แต่ละเจ้า format ต่าง (create charge, **webhook signature**, payload) → normalize เข้า contract เดียวด้วย adapter ใน **Secure Core**:
```
PaymentGateway:
  create_charge(amount, metadata) -> {charge_id, qr}
  verify_webhook(raw_body, headers) -> VerifiedCharge | reject   ← security-critical, ต่างเจ้า
  list_recent(since) -> [...]                                     ← reconciliation
```
- format เฉพาะเจ้าอยู่**ข้างใน adapter**, system ที่เหลือพูด `TipEvent` ปกติ
- ⚠️ **adapter = Secure Core (hook-protected) ไม่ใช่ Safe Edge** — เพราะ `verify_webhook` เป็นด่านหลัก → **เพิ่ม gateway = reviewed contribution ไม่ใช่ vibecode/config toggle**
- **startup self-test (§13.2) ยิง bad-signature vector ของทุก adapter ที่เปิด** — กัน adapter ใหม่ verify หละหลวม
- **PoC**: 🔧[rev 2026-06-05] **มี 2 adapters หลัง interface นี้แล้ว** — `core/payment/omise.py` + `core/payment/stripe.py`, เลือกด้วย `PAYMENT_GATEWAY` ใน `main.py` (**if/else ไม่มี registry** — seam ไม่ใช่ framework). `core/payment/base.py` = `PaymentGateway` Protocol + `WebhookEvent` (normalized) — webhook route branch บน `WebhookEvent.kind` ไม่เห็น payload เฉพาะเจ้า. **Stripe ที่ต่างจาก Omise:** sig = `Stripe-Signature: t=,v1=`, `whsec_` ใช้ **as-is ไม่ base64** (Omise = base64-decode), signed = `<t>.<raw_body>`, success event `payment_intent.succeeded`; PromptPay server-side ได้ (no Stripe.js — ยืนยันด้วย test-mode spike) แต่ **บังคับ `payment_method_data[billing_details][email]`** → adapter ใส่ placeholder (`receipt_email`, override ได้). `secrets.validate` + startup self-test (§13.2) bind ตาม `PAYMENT_GATEWAY` ที่เลือก. fee: Stripe TH PromptPay 1.65% ≈ Omise → value = ทางเลือก provider. card (Omise.js/Stripe.js) ยัง **roadmap**.

---

## 10. Deployment topology

ขั้นตอน (รายละเอียดเต็มใน README/guide):
1. **Omise**: สมัครบัญชี (sole proprietor ใช้แค่บัตรประชาชน/ใบขับขี่ได้ — KYC review ~15 วันทำการ, เช็ค prohibited-business ก่อน), เอา pkey/skey (test ก่อน), ตั้ง webhook URL → tunnel + สร้าง webhook secret
2. **Cloudflare**: streamer ลงทะเบียน domain เอง (D9) → เพิ่มเข้า Cloudflare → สร้าง named tunnel → ingress map hostname/path → service, ตั้ง SSL Full + HSTS + Always HTTPS
3. **OBS**: เปิด obs-websocket v5 ตั้ง password, browser source ชี้ overlay URL (+token)
4. **`.env`**: เติม secret ครบ, `chmod 600`, `docker compose up`
5. **ทดสอบ test mode** ก่อน live ตามเกณฑ์ SPEC §11

> domain เลี่ยงไม่ได้สำหรับ named tunnel (URL คงที่ที่ Omise webhook ชี้มา) — `trycloudflare.com` quick tunnel ให้ URL ชั่วคราวที่เปลี่ยนทุก restart → ใช้ test ได้ ไม่เหมาะ production

### 10.1 Container hardening (กัน hijack — ทุก service ใน compose)
| มาตรการ | ทำไม |
|---|---|
| **ไม่ publish port ออก host เลย** (ยกเว้นไม่มี) — service คุยกันผ่าน internal network, มีแต่ `cloudflared` ออกเน็ต (outbound) | ไม่มี inbound surface ให้โจมตี (SPEC §2) |
| `cloudflared` อยู่ network เดียวที่ออกเน็ตได้; `db` + `backend` อยู่ **internal network** ไม่มี egress | จำกัด lateral movement / exfil |
| **non-root user** ทุก container | ลดผลถ้าโดน RCE |
| `read_only: true` rootfs + `tmpfs` เฉพาะ path ที่เขียนจริง | กันฝัง payload |
| `cap_drop: [ALL]` เพิ่มกลับเฉพาะที่จำเป็น | ตัด capability เกิน |
| `security_opt: ["no-new-privileges:true"]` | กัน privilege escalation |
| **resource limits** (mem/cpu/pids) ทุก service | กัน DoS / runaway / fork bomb |
| **ไม่ mount `docker.sock`** เด็ดขาด | mount = เท่ากับให้ root บน host |
| secret ผ่าน `env_file` (chmod 600) ไม่ใช่ build `ARG`/`COPY` (SPEC §4.6) | secret ไม่ติดใน image layer |
| pin base image ด้วย **digest** + lockfile (SPEC §4.9) | กัน supply-chain / image เปลี่ยนใต้เท้า |
| `healthcheck` + `restart: unless-stopped` | ฟื้นเองเมื่อ crash |
| OBS WS ผ่าน `host.docker.internal` (Linux ใช้ `extra_hosts`) ไม่ expose 4455 | port 4455 ห้ามหลุดนอกเครื่อง (SPEC §5) |
| db volume = least-priv mount | จำกัดสิทธิ์ไฟล์ |

### 10.2 Docs set (วางตอนนี้ เขียนตอน build — สำคัญเพราะ target non-tech)
- `README.md` — overview, value prop (+fee honesty §1), DISCLAIMER (KYC/ภาษี/fee เป็นของ deployer)
- `docs/guides/SETUP.md` — guide ทีละขั้นสำหรับ non-tech: Omise (สมัคร+fee+test mode) → Cloudflare+domain → OBS → `.env` → `docker compose up` → ทดสอบตาม SPEC §11
- `AGENTS.md` / `CLAUDE.md` — vibecode guardrails: core ห้ามแตะ, แก้ที่ไหนได้, "แก้เสร็จรัน `make verify`" (โยง §13)
- `SECURITY.md` — trust model, Secure Core คืออะไร, คำเคลมซื่อสัตย์ (§13), วิธี report ช่องโหว่
- `CONFIG.md` — อ้างอิง `settings.json`/env ทุกตัว (โยง config-over-code §13.2)

### 10.3 DB & hosting flexibility — config-flex (D15)
- **DB target = `DATABASE_URL`** (SQLAlchemy + portable schema): `sqlite:///data/...` (เครื่องเดียว) / `postgresql://...@nas` / cloud Postgres → **zero code change**
- **Hosting**: docker-compose ลงได้ทุกที่ที่รัน Docker — stream PC / NAS (Synology,QNAP) / VPS / cloud VM
- ⚠️ **caveat (ซื่อสัตย์)**:
  - **SQLite ห้ามวางบน network share (NFS/SMB)** — locking พัง/corrupt. "DB บน NAS" = **รัน Postgres บน NAS** ไม่ใช่วางไฟล์ SQLite บน share
  - **Cloud DB แลก trust story** — alias/message ออกจากเครื่อง streamer (ไม่ใช่ financial PII—Omise ถือ—แต่ขัด ethos self-host data-ownership §9.3) → เลือกได้ แต่บอก tradeoff
  - **OBS coupling**: `host.docker.internal:4455` สมมติ backend อยู่เครื่องเดียวกับ OBS. ย้าย backend ไป NAS/VPS → OBS คนละเครื่อง → ต้อง reach ข้าม network (อย่า expose 4455 ดิบ; ใช้ LAN/VPN, companion รายงาน live, หรือ manual toggle — live เป็น UX gate §5 degrade ได้)

| สถานการณ์ | ผลลัพธ์ |
|---|---|
| donor จ่าย PromptPay **หลัง stream จบ** | webhook ยังบันทึก (D7), overlay อาจปิดแล้ว → reconciliation/record มีใน DB เงินไม่หาย |
| backend ดับระหว่างมี charge | reconciliation ตอน start ดึง successful กลับมา push (§8.4) |
| Omise ส่ง webhook ซ้ำ | guarded update rowcount=0 → ไม่ push ซ้ำ |
| signature ผิด / ปลอม webhook | 401 ปฏิเสธ |
| charge `failed`/`expired` | update status, ไม่ push, ไม่แสดง |
| overlay disconnect (backend ยัง up) | พลาด live event → reconnect แล้วดึง recent unacked (known gap PoC) |
| OBS ปิด / ws ต่อไม่ได้ | `/live-status` คืน live=false (fail-closed) → tip form ไม่ขึ้น |
| ข้อความ donor มี `<script>` | textContent + CSP → แสดงเป็น text ไม่รัน |
| start โดยไม่มี secret | refuse start + บอกว่าขาดอะไร |

---

## 11. Capacity & limits (🔧[rev 2026-06-03] estimate — ยังไม่ load-test)

> **"concurrent user" ≠ viewer.** viewer อยู่บน Twitch/YT ไม่แตะ backend. overlay = SSE **1 conn local**. backend โดนแค่คน**กำลังจ่าย tip** = เศษเสี้ยวของ viewer → คิดที่ **tip rate** ไม่ใช่ viewer count

**Bottleneck (เรียงตามที่ชนก่อน):**

| ชั้น | เพดาน |
|---|---|
| **Omise API** | **~15–20 charge-create/s** (HTTP 429 ถ้าเกิน; งานใหญ่ติดต่อ Omise ล่วงหน้า) — [rate-limiting](https://docs.omise.co/api-rate-limiting). ✅ design poll status จาก **DB local ไม่ poll Omise** → ตรง best-practice "use webhooks not polling" |
| **CPU เครื่อง stream** | แชร์กับ OBS+เกม → ต้องเบา (resource limit §10.1) = ข้อจริงเชิงปฏิบัติ ไม่ใช่ throughput |
| **SQLite single-writer (WAL)** | พัน+ write/s บน SSD ≫ tip rate จริง → ไม่ชน |
| **FastAPI/uvicorn async** | ร้อย–พัน conn I/O-bound → ไม่ชน |

**ตัวเลข:** tip ใหม่ต่อเนื่อง **~15–20/s** (Omise-bound) · คนค้างจ่าย + poll DB local **หลักร้อยสบาย** · demand จริง streamer ท็อป **<1 tip/s** sustained, burst 2–3/s → architecture เผื่อ **10–20×**

**ที่จะงอ:** viral burst >20 charge/s เฉียด 429 → client jitter + retry-on-429 backoff · pending ค้าง poll → expire หลัง N นาที + poll backoff · ถ้าจะเป็น multi-tenant platform จริง (คนละ use case) → Postgres + เครื่องแยก (D15)

**TODO ก่อนเคลมตัวเลข:** ยิง `k6`/`locust` 1 scenario (burst tip) — อย่าเคลมลอยๆ (ตรง ethos §1 fee-honesty)

---

## 12. Extensibility & anti-abuse (วาง seam ตอนนี้ — build ทีหลัง)

### 12.1 หลักการ: payment gate = ฐานกัน hater
ต่างจาก chat ฟรี — ส่งข้อความได้ **ต้องจ่ายเงินจริง** → economics กลับด้าน: hater เสียเงินทุกครั้งที่ป่วน นี่คือ**ชั้นฐาน** ชั้นอื่น build บนนี้

### 12.2 The seam — `process_tip()` จุดเดียว (D11)
ระหว่าง "verified successful" (§8.3.h) กับ "push" มี hook เดียว:
```
verified charge
  → TipEvent   (contract เสถียร: {charge_id, amount, name, message, paid_at, source_type})
  → process_tip(event) -> ProcessedEvent | DROP | HOLD
  → OverlayEvent    (สิ่งที่ overlay/TTS บริโภค: {name, message, amount, tts_audio_url?, flagged?})
  → push SSE
```
- **PoC**: 🔧[as-built] `process_tip` = **2 stages จริง** — `app/stages/amount_tiers.py` + `app/stages/word_filter.py` (ลำดับ hardcode ใน `app/process_tip.py`). cap/charset ยังทำที่ §7. **ยังไม่ build stage *framework*** (list/registry). stage พัง → fallback ตัด message (§8.3.h) P0#3
- **ทีหลัง**: เปลี่ยนเป็น list ของ stage เรียงกัน แต่ละ stage `(event) -> event | DROP | HOLD` เพิ่มได้โดยไม่แตะ webhook/overlay
- กุญแจ: **contract ของ TipEvent + OverlayEvent ต้องเสถียร** — เผื่อ field `tts_audio_url`, `flagged` ไว้ตั้งแต่แรกแม้ยังไม่ใช้ → เพิ่มฟีเจอร์แล้ว overlay ไม่ break
- ⚠️ **runtime safety (ไม่ใช่แค่ import direction)**: core เรียก stage *หลัง* commit เงิน (§8.3.h) + ห่อ try/except + timeout → **stage พัง = push base tip, เงินไม่หาย, ไม่ block**
- ⚠️ **งานที่เรียก external (TTS) ห้ามอยู่บน sync push path** — push base ก่อน แล้ว enrich async (external API ใน commit path = ทั้งช่องโหว่ reliability + safety)
- **import**: core เรียก stage ผ่าน `contracts/` (dependency inversion) — edge register stage เข้า contract, **core ไม่ import edge ตรงๆ** (กราฟ import สะอาด แต่จำไว้: ตัวการันตีจริงคือ runtime isolation ข้างบน ไม่ใช่ทิศ import)

### 12.3 ชั้นกัน hater (เพิ่มทีละ stage)
| ชั้น | กลไก | PoC? |
|---|---|---|
| payment gate | ต้องจ่ายจริงถึงส่งข้อความ | ✅ ฐาน |
| length/charset cap | จำกัดที่ `POST /charge` | ✅ |
| rate limit `/charge` per IP | กัน flood สร้าง charge | ✅ |
| amount tiers | `< X` ไม่โชว์ข้อความ, `≥ X` โชว์ (config `settings.json`) | 🔧✅ **PoC** (§14 Q6) — ส่วน `≥ Y` → TTS ยังเป็น seam (TTS roadmap) |
| word filter | banned-words list (`settings.json`) → mask/DROP, exact+normalize (เว้นวรรค/ตัวคล้าย), ไม่ทำ ML | 🔧✅ **PoC** (P0#3) |
| moderation hold | HOLD เข้า queue, streamer อนุมัติก่อนโชว์ | seam |
| refund + block | streamer refund charge ของ hater ผ่าน Omise API → คืนเงิน + ตัดแรงจูงใจ | roadmap |

> **amount tiers** = ตัวคุมทรงพลังรองจาก gate: อยากให้คนอ่าน/TTS ต้องจ่ายมากขึ้น → ป่วนแพงขึ้นเรื่อยๆ เป็น deterrent เชิงเศรษฐศาสตร์

### 12.4 TTS provider — strategy interface
```
TTSProvider.synthesize(text, lang) -> audio bytes
  impls (later): GoogleTTS | AzureTTS | ElevenLabs | ...
  เลือกด้วย env: TTS_PROVIDER=none|google|azure|...   (+ key per provider)
flow: process stage → provider → backend cache audio → serve self-hosted
      → OverlayEvent.tts_audio_url → overlay <audio> เล่น (OBS จับเสียง)
```
- **PoC**: `TTS_PROVIDER=none` — interface มี, ยังไม่ build provider จริง
- 🔧[rev 2026-06-03 P1#7] **alert sound เข้า PoC** (≠ TTS) — เสียงเด้งตอนมี tip = `<audio src>` static + path ใน `settings.json`, serve จาก self (`media-src 'self'` มีแล้ว), Safe Edge ล้วน ไม่แตะ core. cost ≈ 0, UX สูง. TTS (provider + async path) คง roadmap
- audio serve จาก **self** → overlay CSP `media-src 'self'` (ไม่เปิด provider domain) → audit สะอาด
- provider key อยู่ backend เท่านั้น (crown jewel เหมือน skey)

### 12.5 ผลต่อ data model (เผื่อรู้ว่าจะงอกตรงไหน — ยังไม่ใส่ใน PoC)
- field อนาคต: `display_status` (shown|held|dropped), `flagged_reason`, `tts_audio_path`
- moderation hold ต้องมี queue table + endpoint อนุมัติ → roadmap

### 12.6 API-first → รองรับ future feature + bot (static ไม่จำกัดการโต)
- frontend/overlay เป็น **static + ผู้บริโภค API** — feature ใหม่ (top-tipper, แสดงสิทธิ/สถานะ) = endpoint ใหม่ + หน้า/widget ใหม่ ไม่ rewrite. หนักขึ้นค่อยเติม build step ทีหลัง (migrate)
- **bot integration seam**: contract ที่เสถียร 2 ตัวคือจุดต่อ bot — **SSE event stream** (bot subscribe tip realtime) + **read API** (`GET /api/tips` recent/top) → bot/ระบบอื่นดึงไปทำต่อได้
- bot read API ใช้ **token แยก** (อ่านอย่างเดียว) ไม่ใช่ skey — PoC ยังไม่ build, แต่ออกแบบ event contract (§12.2) ให้ bot ใช้ได้ตั้งแต่ตอนนี้
- top-tipper/history **ต้อง persist tip** → โยง privacy §9.3 (เก็บ alias/message + retention)

---

## 13. Vibecode safety — Secure Core / Safe Edge

user เป็น streamer ไม่ใช่ coder → จะใช้ AI แก้/ต่อยอด (vibecode). **payment system + vibecode = ความปลอดภัยต้องมาจากโครงสร้าง ไม่ใช่วินัยคนเขียน**

> **เป้าหมายซื่อสัตย์ (ไม่โม้)**: กัน**ความพังโดยไม่ตั้งใจ** (เคสปกติของ vibecode) — **ไม่ใช่ "vibecode-proof"** คนที่ตั้งใจ + AI รื้อ check ออกยังทำได้ แต่ระบบ **fail closed** เมื่อพังโดยอุบัติเหตุ สำหรับ OSS payment tool คำเคลมที่รับผิดชอบคือ "fails closed on accidental damage" ไม่ใช่ "กันได้ทุกกรณี"

### 13.1 แบ่ง 2 โซน (D12)
| **Secure Core** (ห้าม vibecode) | **Safe Edge** (vibecode สบาย) |
|---|---|
| signature verify, secret load, charge create (skey), idempotency, replay window, CORS, startup self-test | overlay look/animation, tip page style, `process_tip` stages, config values |
| = money + secret path | = presentation + ข้อมูลที่ verified แล้ว |

**Guarantee**: ต่อให้ Safe Edge พังเละ → Secure Core invariant ยังแน่น (เงินปลอมไม่ได้, secret ไม่รั่ว, signature ข้ามไม่ได้)

### 13.2 ของจริง — structural enforcement (4 ชั้น ที่บังคับด้วยโครงสร้าง)
1. **Server-set CSP** ⭐ สำคัญสุด — overlay = ที่ vibecode บ่อยสุด (custom alert animation). CSP เข้มตั้งใน **nginx ไม่ใช่ในหน้า**: `default-src 'none'; script-src 'self'; img-src 'self'; connect-src 'self'; media-src 'self'`. → ต่อให้ vibecode เผลอใช้ `innerHTML`, inline handler (`<img onerror=>`) โดน block (ไม่มี `unsafe-inline`) + exfil ออกนอกโดน block (`img-src/connect-src 'self'`). **overlay ปลอดภัยโดยไม่พึ่งว่าโค้ด overlay ถูก**
2. **Fail-closed startup self-test** — ไม่ใช่แค่เช็ค secret มีไหม แต่**ยิง test vector จริง**: ป้อน signature ผิด → assert verify ปฏิเสธ; assert CORS≠`*`; assert debug=off. ถ้า AI refactor verify แล้วพัง → **boot ไม่ขึ้น + บอกว่าพังตรงไหน** (จับเคส "AI แก้ verify แล้วเจ๊ง" ตั้งแต่ boot)
3. **Secrets ไม่อยู่ในพื้นที่แก้ได้** — skey/webhook secret อยู่ `.env` เท่านั้น, frontend/overlay ไม่เห็นโดยออกแบบ → **รั่วไม่ได้เพราะไม่มีให้รั่ว**
4. **Config-over-code** ⭐ headline — customization ปกติ **ไม่ต้องแตะโค้ดเลย**:
   - สี/ฟอนต์/animation → CSS / theme file
   - amount, tier, banned-words, TTS on/off, ข้อความ alert → env หรือ `settings.json`
   - เป้า: customization ปกติของ streamer **ไม่ต้องแก้ Python เลย** → path อันตรายไม่ถูกแตะตั้งแต่ต้น = ลด attack surface มากกว่า guardrail ทั้งหมดรวมกัน

### 13.3 ของนุ่ม — steering (ช่วยเคสปกติ ไม่ใช่กำแพง)
- **AI guidance files**: `AGENTS.md` / `CLAUDE.md` / `.cursorrules` ในrepo บอก AI: ไฟล์ไหน core ห้ามแตะ, แก้ได้ที่ไหน + **"แก้เสร็จรัน `make verify` ถ้าแดง = พัง security invariant ให้ revert"**
- **bridge soft→loop**: ship เกณฑ์ SPEC §11 เป็น test suite รันได้ (`make verify` / `docker compose run tests`) → AGENTS.md ชี้ AI มารันอันนี้ → steering กลายเป็น loop ที่ AI เช็คเอง. test นี้ต้องมีอยู่แล้วเพื่อ §11 → cost เพิ่ม ≈ 0
- 🔧[rev 2026-06-03 P1#4] **`make verify` += `pip-audit`**; image scan (`trivy`) 🔧[as-built] แยกเป็น **`make scan`** (fail บน fixable HIGH/CRITICAL + dated `.trivyignore`) → verify green = "logic ถูก **+ ไม่มี known CVE ใน pin วันนี้**" (verify เดิมเช็ค invariant ไม่เช็ค vuln — §1.1 freshness signal เลยจะมีฟันจริง). CVE ที่ยังไม่มี patch → `.audit-ignore` มี **reason + วันหมดอายุ** = decision ที่จงใจ ไม่ใช่ปิดตาเงียบ
- ⚠️ ข้อจำกัด: พอ prompt ขัด ("tip ไม่ขึ้น แก้ที") AI อาจแตะ core อยู่ดี → นี่คือ steering ไม่ใช่ enforcement (ของจริงอยู่ §13.2)

### 13.4 จงใจไม่ทำ (over-engineer สำหรับ PoC)
sandbox/container แต่ละ stage, per-stage capability system, เซ็น vibecode diff, RBAC — **ข้ามหมด**

### 13.5 Core isolation hook — บังคับถาม user ก่อนแก้ core (⚠️ build ขั้นสุดท้าย) (D13)

> **สถานะ (2026-06-10): hook ยังไม่ติดตั้ง — เจตนา.** owner ต้องการแก้ `core/` ได้อยู่ระหว่างพัฒนา → ปัจจุบัน `core/` คุ้มครองด้วย convention (AGENTS.md + human-review) ไม่ใช่ hook. ติดตั้งเป็น step สุดท้ายก่อน/หลัง open-source ตามแผนเดิมด้านล่าง
ยกระดับ §13.3 จาก steering → **enforcement ที่ชั้น AI-tool**:
- **กลไก**: Claude Code **PreToolUse hook** ship ใน repo (`.claude/settings.json`) match `Edit|Write|MultiEdit` ที่ path ตรงกับ Secure Core → คืน `permissionDecision: "ask"` (หรือ `deny`) → **บังคับ user ยืนยันก่อนเสมอ แม้รันใน automode / bypass-permissions** + AGENTS.md บอก AI ว่า core ห้ามแตะ
- แข็งกว่า AGENTS.md เพราะ block ที่ชั้น tool ไม่ใช่แค่ขอความร่วมมือ → ship ใน repo = ทุกคนที่ vibecode repo นี้ด้วย Claude Code โดน gate อัตโนมัติ
- **ข้อจำกัด (ซื่อสัตย์)**: บังคับได้เฉพาะ **Claude Code** (Cursor ฯลฯ ไม่ honor hook → เหลือแค่ soft rules) + user ลบ hook จาก settings เองได้ → กัน "**automode เผลอแก้ core**" ไม่ใช่กันคนตั้งใจ (สอดคล้องคำเคลม §13)
- ⚠️ **ทำเป็นขั้นตอนสุดท้ายเด็ดขาด**: ถ้าเปิด hook ตั้งแต่ตอน build → จะแก้ core เองไม่ได้ (โดน block). ลำดับ: สร้าง+test Secure Core ให้เสร็จก่อน → แล้วค่อยลง hook ปิดท้าย (เพิ่มเป็น step สุดท้ายใน build order ของ SPEC §10)

### 13.6 File structure = blast radius (กัน agent ทำงานมั่ว)
layout ให้ "core vs edge" ชัดที่ **path** → directory boundary = ที่ที่ hook (§13.5) match + ที่ agent อ่าน context:
```
core/         ← Secure Core (hook-protected, human-review-only)
  payment/      signature verify, charge create, Omise client
  security/     secret load, startup self-test, log redaction
  db/           schema, idempotent record + push-retry
  AGENTS.md     "STOP — security critical, ห้ามแก้, ถาม user"
contracts/    ← interface เล็กๆ ระหว่าง core↔edge (TipEvent, OverlayEvent, stage protocol) — เปลี่ยนน้อย
app/          ← Safe Edge (vibecode สบาย)
  overlay/      template, theme, animation
  tip/          tip page
  stages/       process_tip stages (filter, tts)  ← register เข้า contracts/
  settings.json config-over-code
  AGENTS.md     "แก้ตรงนี้ได้ เสร็จแล้วรัน make verify"
routes/       ← 🔧[as-built] FastAPI route layer — ชั้นบางๆ: webhook/charge route **delegate ลง core ทันที** (verify/charge logic อยู่ใน core ไม่อยู่ใน route), SSE/live-status เรียก app/. ถือเป็น **core-adjacent**: ไม่อยู่ใน hook path แต่แก้ webhook/charge route = ควร review เหมือน core
main.py       ← 🔧[as-built] composition root: เลือก gateway ตาม PAYMENT_GATEWAY, mount routes, รัน startup self-test — core-adjacent เช่นกัน
tests/        ← make verify (security invariants จาก SPEC §11)
AGENTS.md / CLAUDE.md / .cursorrules   ← root: ชี้ทาง + กฎรวม
```
หลักที่บังคับด้วยโครงสร้าง:
- **one-way dependency**: `app/` → `contracts/` → (`core/` ใช้ contracts). **core ไม่ import app**. lint check ใน `make verify`
- **core เล็ก + self-contained** — ไฟล์น้อย, dep น้อย, ไม่เอื้อมไป edge → audit ง่าย (สำคัญตอน fork), hook path list สั้น, agent มี surface พังน้อย, bit-rot ช้า
- **`contracts/` ต้องเล็กจริง** — แค่ dataclass event + stage protocol. พอมี config-loader/registry = กลายเป็น framework ที่บอกว่าจะไม่ทำ
- **AGENTS.md ราย directory** — agent อ่าน context ใกล้ที่ทำงาน, guard ตรงจุด > ไฟล์ root อันเดียว

> **ซื่อสัตย์เรื่องชั้นป้องกัน** (อย่าสับสน): directory split = **steering + audit clarity** (ไม่ใช่ security boundary); hook-on-path = enforcement (Claude Code เท่านั้น); **commit-before-seam + error-isolation + idempotent push-retry = ตัวการันตีจริง ไม่ขึ้นกับ tool**. money-path security อยู่ที่ runtime invariant (verify, commit, secrets-in-env, server-CSP) — hold ทุกกรณีไม่ว่า layout เป็นไง. filesystem แค่ทำให้ "รักษาไว้ + audit" ง่าย
- **hook กัน location, test กัน behavior — ต้องมีทั้งคู่**: hook ปกป้องสิ่งที่อยู่ใน `core/` แต่หยุด edge stage ที่ไป reimplement verify ผิด*นอก* core ไม่ได้ → `make verify` (sig ผิด→401) จับได้ทุกที่ไม่ว่าโค้ดอยู่ไหน

---

## 14. Open questions (อยากให้ยืนยัน)

1. **D2 (สำคัญสุด)**: ยืนยัน PoC เป็น PromptPay-only + สร้าง charge ฝั่ง server + ไม่ใช้ Omise.js ไหม? ถ้าอยากได้ card ตั้งแต่แรกจะกลับไปใช้ Omise.js + SRI ทันที (เปลี่ยนรูปร่าง frontend) 
   -ส่วนมากจะ tip ผ่าน promptpay แต่เนื่องจากเป็น opensouce ส่วนนี้แก้ได้อยู่แล้วถ้าหาก user ต้องการเพิ่มวิธีการชำระเงินก็แก้แค่ส่วน frontend?
   %%review-claude: ตอบ Q — ไม่ใช่แค่ frontend. เพิ่ม payment method (เช่น card) ต้อง: (1) frontend tokenize ฝั่ง client ด้วย Omise.js เพราะ PAN ห้ามแตะ server เรา (2) เพิ่ม PaymentGateway adapter ซึ่งอยู่ใน **Secure Core** + ต้อง review (D14/§9.5) ไม่ใช่ config (3) webhook verify ต่างเจ้า. → frontend + core adapter + review. PromptPay-only PoC: ยืนยัน OK. (note: คุณใช้คำ "tip" เองตรงนี้ → ตรงกับ wording finding ข้างบน)%%
2. **ช่วง amount min–max** ที่เหมาะ? (วางไว้ ฿20–฿100,000) และ message length cap (วางไว้ 200 ตัว) — ตัวเลขนี้โอเคไหมz
   -ขั้นต่ำขอ 10บาท
   %%review-claude: ฿10 ใช้ไม่ได้ — Omise min charge THB = **฿20** (2000 satang) เป็น hard limit ([currency-and-amount](https://docs.omise.co/currency-and-amount)). ตั้ง min = ฿20. max ฿100,000 OK (เพดาน Omise ฿150,000). message cap 200 = OK.%%
3. **overlay token**: ใส่ token ใน URL พอสำหรับ PoC ไหม (overlay เปิด public ผ่าน tunnel ใครรู้ URL อ่าน tip ได้) หรือยังไม่กังวลใน PoC
   -เรื่อง overlay นี่ไม่แน่ใจเพราะว่ามันเคยใช้ obs แต่ไม่ใช่ว่ามันอยู่ local เดียวกันเหรอไม่น่า public ไปข้างนอก
   %%review-claude: คุณคิดถูก + เป็นการ simplify ที่ดี. overlay = OBS browser source รันบนเครื่อง streamer (เครื่องเดียวกับ backend) → ต่อ backend ผ่าน **localhost** ได้ ไม่ต้อง expose ผ่าน tunnel เลย → ลบ attack surface "overlay public" + ปม token-in-URL ทิ้งได้. tunnel เหลือแค่ tip page + webhook. ผล: §5.2/§7 ต้องแก้ (overlay ออกจาก public list), token ยังเก็บไว้เป็น default-deny กันพลาด แต่ไม่ critical แล้ว.
   **remote OBS (คนละ network — สาย tech):** ออกแบบเผื่อ = ใช่ แต่ **ไม่ต้อง build อะไรเพิ่ม seam มีฟรีอยู่แล้ว** ถ้า: (1) overlay page served จาก backend → SSE ต่อแบบ same-origin (relative URL) → OBS ชี้ localhost (local) หรือ public-url (remote) โค้ดเดียวกัน (2) เก็บ `?token=` ไว้ (§7). → remote = **config flip ล้วน** (เปิด /overlay ใน tunnel + ใช้ token), zero code. SSE ผ่าน tunnel ได้ (เหตุผล D4). กับดัก: ตอน simplify เป็น localhost **อย่าลบ token** — นั่นคือ seam, ลบแล้วต้องเขียนใหม่. default=local/no-token-friction, advanced=remote+token (document ใน SETUP, ปม token-in-URL กลับมาเป็นภาระคนเลือกเอง).%%
4. **tip page หลังจ่าย**: poll status endpoint (เลือกไว้) — ต้องการให้ tip page โชว์ "สำเร็จ/หมดเวลา" ด้วยไหม หรือแค่ขึ้น overlay พอ
   -มี feedback ให้ donor รับรู้ได้
5. ingress ของ tunnel: แยก **subdomain** (tip./overlay.) หรือ **path** (/、/overlay) — มี preference ไหม
   -ลองแนะนำมาเพราะว่าไม่รู้ว่า user จะเอา domain ไปทำอะไรอย่างอื่นไหม
   %%review-claude: แนะนำ **path-based** — `/` = tip page, `/webhooks/omise` = webhook. domain เดียว, tunnel config ชิ้นเดียว, ง่ายสุดสำหรับ non-tech. overlay ไม่ต้องมี ingress (ดู Q3 = localhost). ถ้า user อยากเอา domain ไปทำอย่างอื่นด้วย → แยก subdomain (tip.) ทีหลังได้แบบ zero-code (แค่ config Cloudflare) ไม่ต้อง lock ตอนนี้.%%
6. **anti-abuse ใน PoC**: ยืนยันว่า PoC build แค่ชั้นฐาน (gate + cap + rate limit) ใช่ไหม หรืออยากได้ amount-tier / word-filter ตั้งแต่ PoC เลย (กระทบ scope)
   -ขอเลย req นี้ค่อนข้างจำเป็นเนื่องจากจะมีคนที่ tip คำแปลก ๆ มาอ่านให้รำคาญ
   %%review-claude: รับทราบ — **word-filter เลื่อนเข้า PoC** (จากเดิม future §12.3). กระทบ scope: เพิ่ม `banned_words` ใน settings.json + 1 stage ใน `process_tip()` seam (D11/§12.3) ที่กรอง/mask ก่อน push. ฐาน gate+cap+rate-limit เดิมยังอยู่. ของจริงเขียนตอน build (Q11 = ออกแบบก่อน). (note: คุณใช้ "tip" อีกแล้ว → wording finding)%%
7. **TTS provider ตัวแรก** ที่อยากรองรับ (Google / Azure / ElevenLabs / อื่น) — ไว้ออกแบบ interface ให้ตรง
   -ไม่แน่ใจว่าส่วนมากใช้อะไร แต่ขอ google
8. **config surface**: เห็นด้วยไหมว่า config หลัก (amount/tier/สี/ข้อความ/banned-words) ควรอยู่ใน `settings.json` + CSS theme เดียว เพื่อให้ vibecode ไม่ต้องแตะ Python — มีอะไรอยากให้เป็น config เพิ่ม
   -อยากให้อิสระหน่อย เพราะว่าบางคนอาจต้องการ custom ได้เต็มที่ ทำ interface แยก?
9. **privacy retention** (§9.3): persist alias+message + auto-purge 90 วัน (เพื่อให้มี top-tipper/bot) — โอเคไหม หรืออยาก max-privacy ไม่ persist message (จะทำ top-tipper/history ไม่ได้)? เลข purge กี่วัน?
   -แล้วแต่ user เนื่องจากข้อมูลปัจจุบันไม่ได้กระทบ PDPA ดังนั้นยังไงก็ได้
10. **ใครรับภาระ fee** Omise (PromptPay 1.65%+VAT): หักจากยอด streamer (default) หรือบวกเพิ่มให้ donor จ่าย? กระทบ logic คำนวณ amount
    -หักจาก streamer เลย หรืออาจจะทำตัวเลือกให้ donor เลือกที่จะจ่าย fee ให้ได้ด้วยเพื่อจะได้ให้เงิน streamer เต็มจำนวน
11. **scope รอบนี้**: logs/docs ยืนยันแค่ **ออกแบบ policy + วาง doc set** ตอนนี้ (เขียนจริงตอน build) ใช่ไหม หรืออยากให้เขียน SETUP/AGENTS เต็มเลยรอบนี้
    -เอาแค่ออกแบบก่อน ยังไม่ต้องเต็มมาก

---

## 15. Roadmap (post-PoC — ยังไม่ทำ)

ฟีเจอร์ table-stakes ของ TipMe ที่ผู้ใช้จะคาดหวัง (build ทีหลัง ไม่ใช่ตอนนี้ ตาม SPEC §9):
- **Tip Goal** bar, **Top Tipper**, **Latest Tip**
- alert **image** (sound = เข้า PoC แล้ว §12.4), **TTS** อ่านข้อความ
- 🔧[rev 2026-06-03] **donor-pays-fee toggle** (donor เลือกจ่าย Omise fee ให้ streamer ได้เต็มจำนวน — §14 Q10)
- **Card** payment (กลับมาใช้ Omise.js + SRI)
- payment methods เพิ่ม (TrueMoney Wallet ฯลฯ ที่ Omise รองรับ)
- ย้าย SQLite → Postgres (schema เผื่อไว้แล้ว)
- Docker secrets / Vault (advanced option)

---

อ้างอิง Omise: [Webhooks](https://docs.omise.co/api-webhooks) · [PromptPay](https://docs.omise.co/promptpay) · [Enable live account/KYC](https://docs.omise.co/how-do-i-enable-live-account) · [Prohibited businesses](https://docs.omise.co/prohibited-businesses)
