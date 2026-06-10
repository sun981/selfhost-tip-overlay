# user/ — ของคุณ โฟลเดอร์เดียวที่ควรแก้

ทุกไฟล์ในโฟลเดอร์นี้ (ยกเว้น README กับไฟล์ `.example`) **ไม่ถูก track โดย git**
— อัปเดตระบบด้วย `git pull` หรือ `docker compose pull` ได้โดยของที่คุณแก้ไม่หาย

| ไฟล์ | ทำอะไร |
|---|---|
| `settings.json` | ตั้งค่า: คำต้องห้าม, ขั้นต่ำโชว์ข้อความ, ฯลฯ — copy จาก `settings.example.json` แล้วแก้เฉพาะ key ที่อยากเปลี่ยน (key ที่ไม่ใส่ใช้ค่า default) |
| `web/theme.css` | แต่งหน้า tip page + overlay — โหลดทับ style เดิม สร้างไฟล์เมื่อไหร่มีผลเมื่อนั้น |
| `web/sounds/alert.wav` | เสียงแจ้งเตือนของคุณเอง — ถ้ามีไฟล์นี้ระบบใช้แทนเสียง default |

ข้อควรรู้:

- `settings.json` ทับเป็นราย key บนสุด: ถ้าจะแก้อะไรใน `amount_tiers`
  ต้อง copy ทั้งก้อน `amount_tiers` มา
- แก้ `settings.json` แล้วต้อง restart backend: `docker compose restart backend`
- theme/เสียง แค่ refresh browser source ใน OBS
- ห้ามเก็บ secret ในโฟลเดอร์นี้ — secret อยู่ใน `.env` เท่านั้น

วิธีแก้แบบปลอดภัยด้วย AI ดู `docs/guides/VIBECODE.md`
