"""
EWA — ทดสอบ fetch_ohlcv จริง (รันบน Hermes เท่านั้น)
======================================================
สิ่งที่ต้องเตรียมก่อนรัน:
  1. เปิด TradingView ด้วย --remote-debugging-port=9222
     PowerShell: Start-Process "TradingView.exe" -ArgumentList "--remote-debugging-port=9222"
  2. ให้ TradingView window อยู่ foreground
  3. รัน: python scripts/test_fetch.py

output:
  - print สรุป 5 แถวแรก + สุดท้าย
  - save CSV ที่ data/samples/BTCUSDT_60.csv สำหรับ dev เฟส 3
"""

import sys
import logging
from pathlib import Path

# เพิ่ม root ของโปรเจคใน path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.tv_client import fetch_ohlcv, TVConnectionError, TVDataError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("test_fetch")


def main():
    SYMBOL = "BTCUSDT"
    TIMEFRAME = "60"   # 1H
    BARS = 200

    print("=" * 60)
    print(f"EWA — test_fetch.py")
    print(f"Symbol    : {SYMBOL}")
    print(f"Timeframe : {TIMEFRAME} (1H)")
    print(f"Bars      : {BARS}")
    print("=" * 60)
    print()
    print("กำลัง fetch... (TradingView ต้อง foreground)")
    print()

    try:
        df = fetch_ohlcv(SYMBOL, TIMEFRAME, BARS)
    except TVConnectionError as e:
        print(f"[ERROR] MCP ไม่ตอบ: {e}")
        print()
        print("แก้ไข:")
        print("  1. เปิด TradingView ด้วย --remote-debugging-port=9222")
        print("  2. ให้ window อยู่ foreground")
        print("  3. รัน script นี้ใหม่")
        sys.exit(1)
    except TVDataError as e:
        print(f"[ERROR] data ผิดรูปแบบ: {e}")
        sys.exit(1)

    # --- สรุปผล ---
    print(f"✓ ได้ {len(df)} แท่ง")
    print(f"  ช่วงเวลา : {df['time'].iloc[0]} → {df['time'].iloc[-1]}")
    print(f"  Timezone  : {df['time'].dt.tz}")
    print(f"  fetched_at: {df.attrs.get('fetched_at', 'N/A')}")
    print(f"  symbol    : {df.attrs.get('symbol', 'N/A')}")
    print(f"  timeframe : {df.attrs.get('timeframe', 'N/A')}")
    print()

    print("--- 5 แท่งแรก ---")
    print(df.head().to_string(index=False))
    print()
    print("--- 5 แท่งสุดท้าย ---")
    print(df.tail().to_string(index=False))
    print()

    # --- Save CSV ---
    out_dir = ROOT / "data" / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{SYMBOL}_{TIMEFRAME}.csv"
    df.to_csv(out_path, index=False)
    print(f"✓ บันทึก CSV: {out_path}")
    print("  (ใช้ไฟล์นี้ dev เฟส 3 โดยไม่ต้องพึ่ง TradingView)")


if __name__ == "__main__":
    main()
