"""
EWA - Elliott Wave Classifier (Week 2)
========================================
รับ pivot sequence จาก pivot_engine.py แล้วจำแนกว่าน่าจะเป็น pattern แบบไหน
(Impulse 1-2-3-4-5 หรือ Zigzag A-B-C) พร้อมคำนวณ confidence score

หมายเหตุ: นี่คือ "ตัวช่วยกรอง" ไม่ใช่การนับ wave ที่สมบูรณ์แบบ
ผลลัพธ์ควรนำไปดูกราฟจริงประกอบการตัดสินใจเสมอ
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class WaveAnalysis:
    pattern: str                  # "impulse" | "zigzag" | "unknown"
    direction: str                # "up" | "down"
    current_wave: str             # เช่น "Wave4", "WaveB", "Wave5 (in progress)"
    confidence: int                # 0-100
    notes: list = field(default_factory=list)   # เหตุผล/รายละเอียดการคำนวณ
    next_setup: Optional[str] = None             # เช่น "W5 Setup", "Zigzag C Setup"
    fib_zone: Optional[dict] = None              # zone ที่คาดว่า wave ถัดไปจะจบ


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _pct_retrace(start, end, point):
    """คำนวณ % retracement ของ 'point' เทียบกับ swing start->end"""
    total = end - start
    if total == 0:
        return 0.0
    return abs((end - point) / total) * 100


def _wave_len(p1, p2):
    return abs(p2 - p1)


# ---------------------------------------------------------------------------
# Impulse Classifier (1-2-3-4-5)
# ---------------------------------------------------------------------------

def classify_impulse(pivots: list) -> Optional[WaveAnalysis]:
    """
    ต้องการ pivot อย่างน้อย 6 จุด (Start, W1, W2, W3, W4, W5)
    pivots = [{'type': 'H'/'L', 'price': float}, ...] เรียงตามเวลา (เก่า -> ใหม่)
    """
    if len(pivots) < 5:
        return None

    # ใช้ pivot 6 จุดล่าสุด (หรือน้อยกว่าถ้ายังไม่ครบ 5)
    last = pivots[-6:] if len(pivots) >= 6 else pivots[-5:]
    prices = [p["price"] for p in last]

    notes = []
    score = 0
    max_score = 0

    if len(prices) == 6:
        p0, p1, p2, p3, p4, p5 = prices
        direction = "up" if p1 > p0 else "down"

        w1 = _wave_len(p0, p1)
        w2 = _wave_len(p1, p2)
        w3 = _wave_len(p2, p3)
        w4 = _wave_len(p3, p4)
        w5 = _wave_len(p4, p5)

        # Rule 1: Wave2 ไม่ retrace เกิน 100% ของ Wave1
        max_score += 30
        w2_retrace = _pct_retrace(p0, p1, p2)
        if w2_retrace < 100:
            score += 30
            notes.append(f"Wave2 retrace {w2_retrace:.1f}% ของ Wave1 (ผ่าน: <100%)")
        else:
            notes.append(f"Wave2 retrace {w2_retrace:.1f}% เกิน 100% — ผิดกฎ Impulse")

        # Rule 2: Wave3 ยาวที่สุด (ไม่ใช่ wave สั้นสุดในบรรดา 1,3,5)
        max_score += 30
        if w3 >= w1 and w3 >= w5:
            score += 30
            notes.append(f"Wave3 ({w3:.2f}) ยาวที่สุดเมื่อเทียบกับ Wave1 ({w1:.2f}) และ Wave5 ({w5:.2f})")
        elif w3 > min(w1, w5):
            score += 15
            notes.append(f"Wave3 ({w3:.2f}) ไม่ใช่สั้นสุด แต่ไม่ได้ยาวสุด")
        else:
            notes.append(f"Wave3 ({w3:.2f}) สั้นสุด — ผิดกฎ Impulse (ห้าม Wave3 สั้นสุด)")

        # Rule 3: Wave4 ไม่ overlap กับ Wave1 (สำหรับ direction up: low ของ W4 ต้อง > high ของ W1)
        max_score += 25
        if direction == "up":
            overlap = p4 < p1
        else:
            overlap = p4 > p1
        if not overlap:
            score += 25
            notes.append("Wave4 ไม่ overlap กับ Wave1 (ผ่านกฎ)")
        else:
            notes.append("Wave4 overlap กับ Wave1 — ผิดกฎ Impulse ปกติ (อาจเป็น Diagonal)")

        # Rule 4: Wave5 vs Wave3 -> ตรวจ Truncated
        max_score += 15
        truncated = False
        if direction == "up":
            truncated = p5 <= p3
        else:
            truncated = p5 >= p3
        if not truncated:
            score += 15
            notes.append("Wave5 ทำ new high/low เกิน Wave3 (Impulse ปกติ)")
        else:
            notes.append("Wave5 ไม่เกิน Wave3 -> อาจเป็น Truncated 5th")

        confidence = int(score / max_score * 100)

        current_wave = "Wave5 (เสร็จสมบูรณ์)" if not truncated else "Wave5 (Truncated)"
        next_setup = None
        fib_zone = None

        # คาดการณ์ setup ถัดไป: ถ้า Wave5 จบแล้ว มักตามด้วย Corrective ABC
        if confidence >= 50:
            next_setup = "Corrective ABC Setup (รอ Wave A เริ่ม)"

        return WaveAnalysis(
            pattern="impulse",
            direction=direction,
            current_wave=current_wave,
            confidence=confidence,
            notes=notes,
            next_setup=next_setup,
            fib_zone=fib_zone,
        )

    elif len(prices) == 5:
        # มีแค่ 5 จุด -> น่าจะอยู่ระหว่าง Wave4 (รอ Wave5)
        p0, p1, p2, p3, p4 = prices
        direction = "up" if p1 > p0 else "down"

        w1 = _wave_len(p0, p1)
        w2 = _wave_len(p1, p2)
        w3 = _wave_len(p2, p3)
        w4 = _wave_len(p3, p4)

        max_score += 30
        w2_retrace = _pct_retrace(p0, p1, p2)
        if w2_retrace < 100:
            score += 30
            notes.append(f"Wave2 retrace {w2_retrace:.1f}% ของ Wave1 (ผ่าน)")
        else:
            notes.append(f"Wave2 retrace {w2_retrace:.1f}% เกิน 100% — ผิดกฎ")

        max_score += 30
        if w3 > w1:
            score += 30
            notes.append(f"Wave3 ({w3:.2f}) ยาวกว่า Wave1 ({w1:.2f})")
        else:
            notes.append(f"Wave3 ({w3:.2f}) ไม่ยาวกว่า Wave1 — น่าสงสัย")

        max_score += 25
        if direction == "up":
            overlap = p4 < p1
        else:
            overlap = p4 > p1
        if not overlap:
            score += 25
            notes.append("Wave4 ไม่ overlap Wave1 (ผ่านกฎ)")
        else:
            notes.append("Wave4 overlap Wave1 — ผิดกฎ Impulse ปกติ")

        confidence = int(score / max_score * 100) if max_score else 0

        # คาดการณ์ Wave5 ด้วย Fib extension
        w4_retrace = _pct_retrace(p2, p3, p4)
        fib_zone = {
            "wave4_retrace_pct": round(w4_retrace, 1),
            "expect_w5_target_1.0x": round(p4 + (p3 - p2) * (1 if direction == "up" else -1), 2),
            "expect_w5_target_1.618x": round(p4 + (p3 - p2) * 1.618 * (1 if direction == "up" else -1), 2),
        }
        notes.append(f"Wave4 retrace {w4_retrace:.1f}% ของ Wave3")

        next_setup = "W5 Setup" if confidence >= 50 and 30 <= w4_retrace <= 50 else None

        return WaveAnalysis(
            pattern="impulse",
            direction=direction,
            current_wave="Wave4 -> รอ Wave5",
            confidence=confidence,
            notes=notes,
            next_setup=next_setup,
            fib_zone=fib_zone,
        )

    return None


# ---------------------------------------------------------------------------
# Zigzag Classifier (A-B-C)
# ---------------------------------------------------------------------------

def classify_zigzag(pivots: list) -> Optional[WaveAnalysis]:
    """
    ต้องการ pivot อย่างน้อย 3 จุด (Start->A, A->B, B->C หรือกำลังอยู่ B รอ C)
    """
    if len(pivots) < 3:
        return None

    last = pivots[-4:] if len(pivots) >= 4 else pivots[-3:]
    prices = [p["price"] for p in last]

    notes = []
    score = 0
    max_score = 0

    if len(prices) == 4:
        p0, pa, pb, pc = prices
        direction = "up" if pa > p0 else "down"  # ทิศของ wave A

        wave_a = _wave_len(p0, pa)
        wave_c = _wave_len(pb, pc)

        # Rule 1: B retrace 38.2-78.6% ของ A
        max_score += 50
        b_retrace = _pct_retrace(p0, pa, pb)
        if 38.2 <= b_retrace <= 78.6:
            score += 50
            notes.append(f"Wave B retrace {b_retrace:.1f}% ของ Wave A (ผ่าน: 38.2-78.6%)")
        else:
            notes.append(f"Wave B retrace {b_retrace:.1f}% อยู่นอกช่วง 38.2-78.6%")

        # Rule 2: C ความยาวใกล้เคียง A (0.618x - 1.618x)
        max_score += 50
        ratio_c_a = wave_c / wave_a if wave_a != 0 else 0
        if 0.618 <= ratio_c_a <= 1.618:
            score += 50
            notes.append(f"Wave C/A ratio = {ratio_c_a:.2f} (อยู่ในช่วงปกติ 0.618-1.618)")
        else:
            notes.append(f"Wave C/A ratio = {ratio_c_a:.2f} (นอกช่วงปกติ)")

        confidence = int(score / max_score * 100)

        return WaveAnalysis(
            pattern="zigzag",
            direction=direction,
            current_wave="Wave C (เสร็จสมบูรณ์)",
            confidence=confidence,
            notes=notes,
            next_setup="รอ Impulse ใหม่ทิศตรงข้าม Wave C" if confidence >= 50 else None,
        )

    elif len(prices) == 3:
        p0, pa, pb = prices
        direction = "up" if pa > p0 else "down"

        max_score += 100
        b_retrace = _pct_retrace(p0, pa, pb)
        if 38.2 <= b_retrace <= 78.6:
            score += 100
            notes.append(f"Wave B retrace {b_retrace:.1f}% ของ Wave A (ผ่าน: 38.2-78.6%)")
        else:
            notes.append(f"Wave B retrace {b_retrace:.1f}% อยู่นอกช่วง 38.2-78.6%")

        confidence = int(score / max_score * 100)

        wave_a = _wave_len(p0, pa)
        fib_zone = {
            "wave_b_retrace_pct": round(b_retrace, 1),
            "expect_c_target_1.0x": round(pb + wave_a * (1 if direction == "up" else -1), 2),
            "expect_c_target_1.618x": round(pb + wave_a * 1.618 * (1 if direction == "up" else -1), 2),
        }

        next_setup = "Zigzag C Setup" if confidence >= 50 else None

        return WaveAnalysis(
            pattern="zigzag",
            direction=direction,
            current_wave="Wave B -> รอ Wave C",
            confidence=confidence,
            notes=notes,
            next_setup=next_setup,
            fib_zone=fib_zone,
        )

    return None


# ---------------------------------------------------------------------------
# Main entry: วิเคราะห์ pivot sequence แล้วเลือก pattern ที่ confidence สูงสุด
# ---------------------------------------------------------------------------

def analyze(pivots: list) -> dict:
    """
    pivots: list of dict {'type': 'H'/'L', 'price': float, ...} (จาก pivot_engine.get_pivot_sequence)

    Returns dict: {'best': WaveAnalysis, 'all': [WaveAnalysis, ...]}
    """
    results = []

    impulse = classify_impulse(pivots)
    if impulse:
        results.append(impulse)

    zigzag = classify_zigzag(pivots)
    if zigzag:
        results.append(zigzag)

    if not results:
        return {"best": None, "all": []}

    best = max(results, key=lambda r: r.confidence)
    return {"best": best, "all": results}


def print_analysis(result: dict):
    best = result["best"]
    if best is None:
        print("ข้อมูล pivot ไม่พอสำหรับการวิเคราะห์ (ต้องการอย่างน้อย 3 จุด)")
        return

    print(f"Pattern: {best.pattern.upper()}  |  ทิศทาง: {best.direction}  |  Confidence: {best.confidence}/100")
    print(f"สถานะปัจจุบัน: {best.current_wave}")
    print("-" * 60)
    for n in best.notes:
        print(f"  - {n}")
    if best.fib_zone:
        print("\nFib zone คาดการณ์:")
        for k, v in best.fib_zone.items():
            print(f"  {k}: {v}")
    if best.next_setup:
        print(f"\n>> Setup ถัดไปที่น่าจับตา: {best.next_setup}")
    else:
        print("\n>> ยังไม่เข้า setup ที่กำหนดไว้")

    if len(result["all"]) > 1:
        print("\n(ผลลัพธ์อื่นที่เป็นไปได้):")
        for r in result["all"]:
            if r is not best:
                print(f"  - {r.pattern}: confidence {r.confidence}/100, สถานะ: {r.current_wave}")


# ---------------------------------------------------------------------------
# ทดสอบด้วยข้อมูลจำลอง (ต่อจาก pivot_engine.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # ตัวอย่าง pivot sequence แบบ Impulse 1-2-3-4-5 (จากผลทดสอบ pivot_engine.py)
    impulse_pivots = [
        {"type": "L", "price": 100.00},  # Start
        {"type": "H", "price": 120.83},  # Wave1
        {"type": "L", "price": 109.10},  # Wave2
        {"type": "H", "price": 150.86},  # Wave3
        {"type": "L", "price": 134.02},  # Wave4
        {"type": "H", "price": 165.70},  # Wave5
    ]

    print("=== ทดสอบกับ Impulse Wave (1-2-3-4-5) ===\n")
    result = analyze(impulse_pivots)
    print_analysis(result)

    print("\n\n=== ทดสอบกับ Impulse ที่ยังไม่ครบ (รอ Wave5) ===\n")
    impulse_incomplete = impulse_pivots[:5]  # ตัด Wave5 ออก
    result2 = analyze(impulse_incomplete)
    print_analysis(result2)

    print("\n\n=== ทดสอบกับ Zigzag (A-B-C) ที่ยังไม่ครบ (รอ Wave C) ===\n")
    zigzag_pivots = [
        {"type": "H", "price": 165.70},  # Start (จุดสูงสุดก่อน correction)
        {"type": "L", "price": 145.00},  # Wave A
        {"type": "H", "price": 158.00},  # Wave B
    ]
    result3 = analyze(zigzag_pivots)
    print_analysis(result3)
