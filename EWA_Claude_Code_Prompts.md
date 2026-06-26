# EWA — Claude Code Prompts (ทุกเฟส)
> ใช้ใน Claude Code บน Hermes เท่านั้น
> ส่งทีละ prompt รอผลจริงก่อน ค่อยส่ง prompt ถัดไป

---

## PROMPT 0 — Setup & Push GitHub
```
อ่าน CLAUDE.md ก่อนเริ่มทุกครั้ง

งาน: ตรวจสอบ repo และ push ขึ้น GitHub ให้เรียบร้อย

สถานะปัจจุบัน:
- repo อยู่ที่ C:\Users\bobco\ewa
- มี commit แล้ว 1 อัน (b26b694)
- remote origin = https://github.com/Bobcole63/EWA.git
- push ไม่ผ่านเพราะ GitHub มี commit อยู่แล้ว (README)

ให้ทำตามลำดับ:
1. cd C:\Users\bobco\ewa
2. git pull origin main --allow-unrelated-histories
3. ถ้ามี merge conflict → จัดการให้ครบ
4. git push -u origin main
5. ยืนยันด้วย git log --oneline
6. รายงานผลจริงจาก terminal เท่านั้น ห้าม fabricate
```

---

## PROMPT 1 — เฟส 1: Data Layer (ถ้ายังไม่เสร็จ)
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: ตรวจสอบเฟส 1 Data Layer ว่าสมบูรณ์

ให้ทำ:
1. อ่านไฟล์จริงใน C:\Users\bobco\ewa\data\ ว่ามีอะไรบ้าง
2. รัน python scripts/test_fetch.py จริง
   (TradingView ต้องเปิดด้วย --remote-debugging-port=9222 และ foreground)
3. ถ้า fetch สำเร็จ → ยืนยัน CSV อยู่ที่ data/samples/BTCUSD_60.csv
4. ถ้า error → รายงาน error จริง ห้ามแต่งผล

ห้าม:
- return ราคาปลอม
- แสดงผล fetch ที่ยังไม่ได้รันจริง
- ข้ามขั้นตอนใด
```

---

## PROMPT 2 — เฟส 2: ตรวจสอบ Pivot Engine
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: ตรวจสอบ pivot_engine.py และรัน backtest จริง

ให้ทำ:
1. อ่าน core/pivot_engine.py ทั้งไฟล์
2. สรุป interface จริง:
   - find_zigzag_pivots() → input/output อะไร
   - get_pivot_sequence() → คืน list หน้าตายังไง
   - fib_levels() → คืน dict หน้าตายังไง
3. รันทดสอบกับ CSV จริงที่มีอยู่:
   python -c "
   import pandas as pd
   from core.pivot_engine import find_zigzag_pivots, get_pivot_sequence, fib_levels
   df = pd.read_csv('data/samples/BTCUSDT_60.csv', parse_dates=['time'])
   df_pivot = find_zigzag_pivots(df, deviation_pct=5.0)
   seq = get_pivot_sequence(df_pivot)
   print(f'pivot count: {len(seq)}')
   for p in seq[-5:]:
       print(p)
   "
4. รายงานผลจริง pivot ที่ได้ (ราคา/เวลา/type) — ห้าม fabricate
```

---

## PROMPT 3 — เฟส 3: Candidate Builder
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: สร้าง core/setup_screener.py — Candidate Builder

บริบท (อ่านก่อนเขียน):
- pivot_engine.py get_pivot_sequence() คืน list of dict: {index, time, type, price}
- เฟสนี้ต้องเป็น deterministic ล้วน ห้าม import LLM

สิ่งที่ต้องทำ:
1. อ่าน core/pivot_engine.py และ core/ew_classifier.py (ถ้ามี) ก่อน
2. สร้าง dataclass Candidate ใน core/setup_screener.py:

{
  "count_label": "impulse" | "zigzag" | "triangle",
  "wave_points": [
    {"label": "1", "price": float, "time": str, "pivot_index": int}
  ],
  "ratios": {"w2_retrace": float, "w3_extension": float},
  "rules_passed": [{"rule": str, "passed": bool, "reason": str}],
  "metadata": {"symbol": str, "timeframe": str, "computed_at": str}
}

3. สร้างฟังก์ชัน build_candidates(pivot_seq, symbol, timeframe) → list[Candidate]
   - sliding window 5-7 pivot ต่อครั้ง
   - ลองตีความเป็น impulse / zigzag / triangle
   - ตรวจ hard rules แต่ละ rule เป็นฟังก์ชันแยก:
     * check_w2_retrace(w1, w2) → bool, reason
     * check_w3_not_shortest(w1, w3, w5) → bool, reason
     * check_w4_no_overlap(w1, w4) → bool, reason
   - ตัด candidate ที่ผิด hard rule ทิ้ง
   - ทุก wave_point ต้องอ้าง pivot_index จริงเท่านั้น

4. สร้าง tests/test_setup_screener.py:
   - ทดสอบแต่ละ hard rule ด้วย pivot ปลอม
   - ครอบ case ที่ควรผ่านและควร reject
   - รัน pytest จริง รายงานผลจริง

5. รัน build_candidates กับ CSV จริง แสดง candidate ที่ได้

ห้าม:
- สร้าง price/time ขึ้นเองโดยไม่มาจาก pivot จริง
- import LLM หรือ external API ในไฟล์นี้
- แสดงผล test ที่ยังไม่ได้รัน
```

---

## PROMPT 4 — เฟส 4: LLM Wave Judge + Validation Gate
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: สร้าง agent/wave_agent.py — LLM Judge + Validation Gate

บริบท (อ่านก่อนเขียน):
- อ่าน core/setup_screener.py เพื่อเข้าใจ Candidate schema จริง
- LLM รับ candidates เป็น JSON ห้ามรับภาพ ห้ามให้ LLM นับเองจากกราฟ

สิ่งที่ต้องทำ:
1. สร้าง judge_candidates(candidates, symbol, timeframe) → WaveJudgement | None
   - ส่ง candidates เป็น JSON ให้ LLM เลือก count ที่ดีที่สุด
   - LLM output ต้องเป็น JSON schema นี้เท่านั้น:
   {
     "selected_index": int,
     "confidence": int (0-100),
     "reasoning": str,
     "alternate": [{"count_label": str, "reason": str}]
   }

2. Validation Gate (ต้องผ่านก่อนใช้ผล):
   - ตรวจ JSON schema ถูกต้องไหม
   - ตรวจทุก wave_point ที่ LLM เลือก ตรง pivot_index จริงในข้อมูลไหม
   - confidence อยู่ใน range 0-100 ไหม
   - ถ้าไม่ผ่าน → reject + log เหตุผล คืน None
   - ห้ามผ่าน Gate โดยไม่ตรวจ

3. ทดสอบจริงกับ candidate จาก CSV จริง
4. รายงานผล: LLM เลือก count อะไร, confidence เท่าไหร่, Gate ผ่านไหม
```

---

## PROMPT 5 — เฟส 5: Chart Renderer
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: สร้าง alert/chart_renderer.py — วาด candlestick + EW overlay

บริบท:
- วาดด้วย mplfinance จาก OHLCV จริง ห้าม screenshot TV
- ทุก overlay วางด้วยค่าราคา/เวลาจริง (data coordinate) เท่านั้น
- ห้ามวาด label จากตัวเลขที่ LLM แต่งหรือยังไม่ผ่าน Gate

สิ่งที่ต้องทำ:
1. ติดตั้ง mplfinance ถ้ายังไม่มี
2. สร้าง render_chart(ohlcv_df, wave_judgement, output_path) → str | None
   Input:
   - ohlcv_df: DataFrame จาก tv_client (time, open, high, low, close, volume)
   - wave_judgement: ผลจาก Validation Gate (ผ่านแล้วเท่านั้น)
   - output_path: path สำหรับบันทึก PNG
   
   Output layers (เปิด/ปิดได้ผ่าน config):
   - candlestick chart
   - wave labels (1,2,3,4,5 / A,B,C) ที่ pivot จริง
   - entry/stop/target เส้นนอน (เขียว/แดง/ฟ้า)
   - Fibonacci levels
   - alternate scenario เส้นประสีเทา
   
   ถ้า wave_judgement ว่าง/None → return None + log ห้ามวาดรูปเปล่า

3. รันจริงกับข้อมูลจาก CSV + wave judgement จริง
4. เปิดรูปให้ดู ยืนยันว่า label อยู่ถูกตำแหน่ง
```

---

## PROMPT 6 — เฟส 6: Alert (Telegram)
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: สร้าง alert/notifier.py — ส่งรูป + ข้อความผ่าน Telegram

บริบท:
- ใช้ TELEGRAM_BOT_TOKEN และ TELEGRAM_CHAT_ID จาก .env
- ส่งเฉพาะ setup ที่ผ่าน Validation Gate + confidence ≥ threshold ใน config
- ต้องมี dedup กัน spam

สิ่งที่ต้องทำ:
1. สร้าง send_alert(chart_path, wave_judgement, symbol, timeframe) → bool
   ข้อความ alert ต้องมี:
   - Symbol, timeframe, pattern, confidence (%)
   - Entry / Stop / Target (พร้อมที่มา)
   - เวลา fetch ข้อมูล (fetched_at)
   - รูปกราฟแนบ
   - Disclaimer: "Screener output — ไม่ใช่คำแนะนำลงทุน"

2. Dedup logic:
   - เก็บ history ของ (symbol, pattern) ที่ส่งแล้ว
   - cooldown ตาม config (default 60 นาที)
   - ถ้าอยู่ใน cooldown → log เท่านั้น ไม่ส่ง

3. ทดสอบจริง: ส่ง test alert ไป Telegram
   ยืนยันว่าได้รับข้อความและรูปจริง

4. ห้ามส่ง alert โดยไม่มีรูปกราฟ
   ห้ามส่ง alert ที่ยังไม่ผ่าน Validation Gate
```

---

## PROMPT 7 — Main Loop
```
อ่าน CLAUDE.md ก่อนเริ่ม

งาน: สร้าง main.py — orchestrator เชื่อมทุกเฟส

ให้ทำ:
1. อ่านทุกโมดูลที่มีอยู่จริงก่อน (tv_client, pivot_engine, setup_screener,
   wave_agent, chart_renderer, notifier) สรุป interface แต่ละตัว
2. สร้าง main loop:
   for each symbol in config[symbols]:
     for each timeframe in config[timeframes]:
       1. fetch OHLCV (tv_client) — ถ้าพัง → log + skip ห้ามใช้ data เก่า
       2. pivot_engine → หา pivot
       3. setup_screener → build candidates
       4. wave_agent → judge + Validation Gate
       5. ถ้าผ่าน Gate + confidence ≥ threshold:
          → chart_renderer → วาดรูป
          → notifier → ส่ง alert (ถ้าไม่อยู่ใน cooldown)
       6. log ทุกขั้น

3. รัน 1 รอบจริงกับ BTCUSDT 1H
4. รายงานผลทุกขั้นจาก log จริง
```

---

## วิธีใช้
1. เปิด Claude Code บน Hermes (`claude` ใน PowerShell ที่ `C:\Users\bobco\ewa`)
2. วาง PROMPT 0 ก่อน → รอผล push GitHub สำเร็จ
3. วาง PROMPT 2 → ตรวจ pivot engine กับ CSV จริง
4. วาง PROMPT 3 → สร้าง Candidate Builder
5. วาง PROMPT 4 → LLM Judge + Gate
6. วาง PROMPT 5 → Chart Render
7. วาง PROMPT 6 → Alert Telegram
8. วาง PROMPT 7 → Main Loop

**กฎสำคัญ:** ถ้า Claude Code แสดงผลโดยไม่ได้รันจริง
ให้ถามกลับ: "รันจริงหรือยัง output นี้มาจากไหน"
