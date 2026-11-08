# Trail vlog — checklist

## ก่อนวิ่ง (บอกผู้ใช้ล่วงหน้า)
- [ ] **Sync เวลากล้อง** กับมือถือ (DJI Mimo → เชื่อมกล้อง) — เวลาในชื่อไฟล์ใช้จับคู่กับ Garmin; ครั้งก่อนกล้องเร็วไป ~13.5 นาที
- [ ] ตั้งกล้อง 4K 16:9 **60fps** + RockSteady (แสงน้อย/ป่าทึบ → 30fps); 200fps เฉพาะช็อต slow-mo ที่ตั้งใจ
- [ ] microSD V30/U3 ≥256 GB แบรนด์แท้ + แบตสำรอง (4K60 ≈ 0.5–0.9 GB/นาที)
- [ ] กด Garmin **Trail Run ตั้งแต่จุดเริ่ม** (ถ้าเริ่มช้า จดไว้ว่ากี่ km)
- [ ] พูดกับกล้องบ่อยๆ: เวลา, จุด checkpoint, ความสูง, ความรู้สึก, มุก — transcript คือวัตถุดิบหลักของการตัด
- [ ] ถ่าย b-roll สั้นๆ: วิว, ทางชัน, ลื่น, อาหาร, สัตว์, เพื่อน — 5–15 วิพอ

## สิ่งที่ต้องได้จากผู้ใช้ก่อนเริ่มตัด
- [ ] path ฟุตเทจ (SD card) + ชื่อ project folder ปลายทาง
- [ ] ไฟล์ Garmin `.FIT` (Garmin Connect → ⚙️ → Export File) — ถ้ามี
- [ ] ชื่องาน/เส้นทาง/ระยะ/ข้อความที่อยากขึ้นจอ, ความยาวที่ต้องการ (default 8–10 นาที)
- [ ] สไตล์เพลง (default: สลับ rock/metal ช่วงแอ็กชัน, pop/chill ช่วงวิว/กิน)
- [ ] ref ภาพ/โปสเตอร์ของงาน (สีธีม, สไตล์ปก) + โลโก้ถ้าอยากใส่
- [ ] API: `XI_KEY` (ElevenLabs: Scribe + Music + SFX), `GETPOD_KEY` (สร้างภาพ) — หรือ generate_image ของ claude-gateway
- [ ] ต้องการไฟล์ส่ง LINE ไหม / ซับเต็มสำหรับ YouTube ไหม

## Deliverables
- [ ] `output/<name>_final.mp4` 4K30 HEVC (~2.5–3 GB / 10 นาที) — QA เฟรม + loudness −14/−15 LUFS
- [ ] `output/<name>_th.srt` ซับไทยเต็ม (แก้คำผิดจาก srt_fixes) — เตือนให้ตรวจใน YouTube Studio
- [ ] `cover/cover_1280.jpg` + `cover_1920.jpg`
- [ ] `output/<name>_LINE_<i>ofN.mp4` 720p ≤3 นาที/ไฟล์ (ถ้าขอ)
- [ ] สรุปเครดิตที่ใช้ (ElevenLabs / image) + เตือน rotate key ที่แปะในแชท
- [ ] ถามก่อนลบไฟล์ชั่วคราว (`work/seg_*`, `work/proxy`)
