"""
EWA - Pivot Detection Engine (ZigZag)
======================================
ตรวจหา Pivot High/Low จากข้อมูล OHLCV โดยใช้ % deviation threshold

Input: รับ OHLCV เป็น list of dict หรือ pandas DataFrame
  columns ที่ต้องมี: time/date, open, high, low, close, (volume optional)

Output: list ของ pivot points แต่ละจุดมี
  - index: ตำแหน่ง bar
  - time: วันที่/เวลา
  - price: ราคา ณ pivot
  - type: 'H' (High) หรือ 'L' (Low)

ใช้งานได้กับข้อมูลจาก TradingView MCP (tv_get_ohlcv) หรือ yfinance
"""

import pandas as pd
import numpy as np


def find_zigzag_pivots(df: pd.DataFrame, deviation_pct: float = 5.0) -> pd.DataFrame:
    """
    หา ZigZag pivots จาก DataFrame ที่มีคอลัมน์ high, low, close

    Parameters
    ----------
    df : DataFrame ที่มี columns: high, low, close (และ index เป็นเวลา หรือมีคอลัมน์ time)
    deviation_pct : % การกลับตัวขั้นต่ำที่จะนับเป็น pivot ใหม่ (default 5%)

    Returns
    -------
    DataFrame ที่มีคอลัมน์เพิ่ม: pivot ('H'/'L'/None), pivot_price
    """
    df = df.reset_index(drop=True).copy()
    n = len(df)

    pivots = [None] * n
    pivot_prices = [np.nan] * n

    if n < 3:
        df["pivot"] = pivots
        df["pivot_price"] = pivot_prices
        return df

    # เริ่มต้น: หาทิศทางแรกจาก high/low ของ bar แรก
    last_pivot_idx = 0
    last_pivot_price = df.loc[0, "close"]
    direction = None  # 'up' หรือ 'down'

    # ใช้ high สำหรับหา pivot high, low สำหรับหา pivot low
    candidate_high_idx = 0
    candidate_high_price = df.loc[0, "high"]
    candidate_low_idx = 0
    candidate_low_price = df.loc[0, "low"]

    for i in range(1, n):
        high = df.loc[i, "high"]
        low = df.loc[i, "low"]

        if direction is None:
            # ยังไม่กำหนดทิศทาง — เช็คว่าราคาขยับเกิน deviation จาก last_pivot_price หรือยัง
            move_up = (high - last_pivot_price) / last_pivot_price * 100
            move_down = (last_pivot_price - low) / last_pivot_price * 100

            if move_up >= deviation_pct:
                direction = "up"
                candidate_high_idx, candidate_high_price = i, high
            elif move_down >= deviation_pct:
                direction = "down"
                candidate_low_idx, candidate_low_price = i, low
            else:
                # อัปเดต candidate ไว้เผื่อ
                if high > candidate_high_price:
                    candidate_high_idx, candidate_high_price = i, high
                if low < candidate_low_price:
                    candidate_low_idx, candidate_low_price = i, low

        elif direction == "up":
            # กำลังหาจุดสูงสุด (pivot high) ต่อไป
            if high > candidate_high_price:
                candidate_high_idx, candidate_high_price = i, high

            # เช็คว่าราคาย่อลงมาเกิน deviation จาก candidate high หรือยัง -> ถ้าใช่ ยืนยัน pivot high
            retrace = (candidate_high_price - low) / candidate_high_price * 100
            if retrace >= deviation_pct:
                pivots[candidate_high_idx] = "H"
                pivot_prices[candidate_high_idx] = candidate_high_price
                last_pivot_idx, last_pivot_price = candidate_high_idx, candidate_high_price
                direction = "down"
                candidate_low_idx, candidate_low_price = i, low

        elif direction == "down":
            # กำลังหาจุดต่ำสุด (pivot low) ต่อไป
            if low < candidate_low_price:
                candidate_low_idx, candidate_low_price = i, low

            # เช็คว่าราคาเด้งขึ้นเกิน deviation จาก candidate low หรือยัง -> ถ้าใช่ ยืนยัน pivot low
            bounce = (high - candidate_low_price) / candidate_low_price * 100
            if bounce >= deviation_pct:
                pivots[candidate_low_idx] = "L"
                pivot_prices[candidate_low_idx] = candidate_low_price
                last_pivot_idx, last_pivot_price = candidate_low_idx, candidate_low_price
                direction = "up"
                candidate_high_idx, candidate_high_price = i, high

    df["pivot"] = pivots
    df["pivot_price"] = pivot_prices
    return df


def get_pivot_sequence(df: pd.DataFrame) -> list:
    """
    ดึง list ของ pivot points ที่ confirmed แล้ว เรียงตามเวลา
    คืนค่าเป็น list of dict: {index, time, type, price}
    """
    result = []
    for i, row in df.iterrows():
        if row["pivot"] in ("H", "L"):
            result.append({
                "index": i,
                "time": row.get("time", i),
                "type": row["pivot"],
                "price": row["pivot_price"],
            })
    return result


def fib_levels(price_a: float, price_b: float) -> dict:
    """
    คำนวณ Fibonacci retracement levels ระหว่างจุด A -> B
    คืนค่า dict ของ % retracement สำคัญ: 23.6, 38.2, 50, 61.8, 78.6
    """
    diff = price_b - price_a
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = {}
    for r in ratios:
        levels[f"{r*100:.1f}%"] = price_b - diff * r
    return levels


def fib_extension(price_a: float, price_b: float, price_c: float) -> dict:
    """
    คำนวณ Fibonacci extension จาก wave A-B โปรเจคจากจุด C
    ใช้สำหรับประมาณเป้า Wave3 หรือ Wave C
    """
    diff = price_b - price_a
    ratios = [1.0, 1.272, 1.618, 2.0, 2.618]
    levels = {}
    for r in ratios:
        levels[f"{r:.3f}x"] = price_c + diff * r
    return levels


# ---------------------------------------------------------------------------
# ตัวอย่างการใช้งานกับข้อมูลจาก yfinance (ทดสอบ logic ก่อนต่อ TradingView MCP)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import yfinance as yf

    symbol = "AAPL"
    print(f"กำลังดึงข้อมูล {symbol} (Daily, 1 ปี)...")
    data = yf.download(symbol, period="1y", interval="1d", progress=False, auto_adjust=True)

    # yfinance คืน MultiIndex columns ถ้าดึงหลาย ticker — ปรับให้เป็น single level
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    data.columns = [c.lower() for c in data.columns]
    data = data.rename(columns={"date": "time"})

    print(f"จำนวน bar: {len(data)}")

    # ทดสอบหา pivot ด้วย deviation 5%
    df_pivots = find_zigzag_pivots(data, deviation_pct=5.0)
    pivot_seq = get_pivot_sequence(df_pivots)

    print(f"\nพบ pivot จำนวน {len(pivot_seq)} จุด (deviation 5%):")
    print("-" * 60)
    for p in pivot_seq:
        time_str = pd.Timestamp(p["time"]).strftime("%Y-%m-%d")
        print(f"  {time_str} | {p['type']} | ราคา: {p['price']:.2f}")

    # แสดงตัวอย่างการคำนวณ Fib retracement จาก pivot 2 จุดล่าสุด
    if len(pivot_seq) >= 2:
        last_two = pivot_seq[-2:]
        a, b = last_two[0]["price"], last_two[1]["price"]
        print(f"\nFib Retracement จาก {a:.2f} -> {b:.2f}:")
        for level, price in fib_levels(a, b).items():
            print(f"  {level}: {price:.2f}")
