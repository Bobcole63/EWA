"""
EWA — Data Layer: TradingView MCP Client
=========================================
ดึง OHLCV จาก TradingView ผ่าน MCP tool tv_get_ohlcv
(TradingView ต้องเปิดด้วย --remote-debugging-port=9222 และ window ต้อง foreground)

workflow:
  1. tv_change_symbol  → เซ็ต symbol บน chart
  2. tv_change_timeframe → เซ็ต timeframe บน chart
  3. tv_get_ohlcv(bars) → ดึง OHLCV จาก chart ที่ active

ห้าม fabricate ราคา — ถ้า MCP ไม่ตอบให้ raise ทันที
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)

# ชื่อ tool จริงใน index.js
_TOOL_CHANGE_SYMBOL = "tv_change_symbol"
_TOOL_CHANGE_TIMEFRAME = "tv_change_timeframe"
_TOOL_GET_OHLCV = "tv_get_ohlcv"
_MAX_BARS = 500  # จำกัดโดย MCP server


class TVConnectionError(Exception):
    """TradingView MCP ไม่ตอบ หรือ port 9222 ไม่พร้อม"""


class TVDataError(Exception):
    """ดึง OHLCV ได้แต่ข้อมูลไม่ครบหรือ format ผิด"""


def _parse_tool_text(tool_name: str, text: str) -> dict:
    lines = [line.strip() for line in text.splitlines()]
    if tool_name != _TOOL_GET_OHLCV:
        return {"ok": True, "text": text}

    symbol = None
    resolution = None
    candles = []
    in_ohlcv = False

    for line in lines:
        if not line:
            continue
        if line.startswith("Symbol:"):
            symbol = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Resolution:"):
            resolution = line.split(":", 1)[1].strip()
            continue
        if line == "## OHLCV":
            in_ohlcv = True
            continue
        if not in_ohlcv or line.startswith("## ") or line == "time,open,high,low,close,volume":
            continue

        parts = line.split(",")
        if len(parts) < 5:
            continue
        candles.append(
            {
                "time": parts[0],
                "open": parts[1],
                "high": parts[2],
                "low": parts[3],
                "close": parts[4],
                "volume": parts[5] if len(parts) > 5 and parts[5] != "" else None,
            }
        )

    return {
        "ok": True,
        "symbol": symbol,
        "resolution": resolution,
        "candles": candles,
        "raw_text": text,
    }


async def _call_mcp_tool_async(tool_name: str, params: dict, mcp_script: str) -> dict:
    server = StdioServerParameters(
        command="node",
        args=[mcp_script],
        cwd=str(Path(mcp_script).resolve().parent),
    )
    try:
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool_name,
                    params,
                    read_timeout_seconds=timedelta(seconds=20),
                )
                if result.isError:
                    raise TVConnectionError(f"MCP tool '{tool_name}' error: {result}")
                text = "\n".join(
                    item.text for item in result.content if getattr(item, "type", None) == "text"
                )
                if not text:
                    return {"ok": True, "text": ""}
                return _parse_tool_text(tool_name, text)
    except FileNotFoundError as e:
        raise TVConnectionError(f"ไม่พบ Node.js หรือ MCP script ที่ {mcp_script}") from e
    except TimeoutError as e:
        raise TVConnectionError(
            f"MCP tool '{tool_name}' timeout — TradingView foreground อยู่ไหม? port 9222 เปิดอยู่ไหม?"
        ) from e
    except Exception as e:
        raise TVConnectionError(f"MCP tool '{tool_name}' error: {e}") from e


def _call_mcp_tool(tool_name: str, params: dict, mcp_script: str) -> dict:
    """
    เรียก MCP tool ผ่าน stdio MCP client
    คืน dict ของ result หรือ raise TVConnectionError ถ้าพัง
    """
    return asyncio.run(_call_mcp_tool_async(tool_name, params, mcp_script))


def _parse_candles(candles: list, symbol: str, timeframe: str) -> pd.DataFrame:
    """
    แปลง candles list จาก MCP → DataFrame สะอาด

    Parameters
    ----------
    candles   : list of dict/list จาก tv_get_ohlcv
    symbol    : ชื่อ symbol (สำหรับ metadata)
    timeframe : timeframe (สำหรับ metadata)

    Returns
    -------
    DataFrame คอลัมน์: time, open, high, low, close, volume
    index: 0-based int, เรียงเก่า→ใหม่

    Raises
    ------
    TVDataError : candles ว่าง หรือ format ผิด
    """
    if not candles:
        raise TVDataError("candles ว่าง — ไม่มีข้อมูล OHLCV")

    rows = []
    for c in candles:
        try:
            if isinstance(c, dict):
                rows.append({
                    "time": c["time"],
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c.get("volume", 0)),
                })
            elif isinstance(c, (list, tuple)) and len(c) >= 5:
                rows.append({
                    "time": c[0],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]) if len(c) > 5 else 0.0,
                })
            else:
                logger.warning(f"candle format ไม่รู้จัก ข้าม: {c}")
        except (KeyError, ValueError, IndexError) as e:
            logger.warning(f"parse candle ล้มเหลว ข้าม: {c} — {e}")

    if not rows:
        raise TVDataError("parse candles ไม่ได้เลยสักแถว — format ผิดทั้งหมด")

    df = pd.DataFrame(rows)

    # แปลง time → datetime UTC
    if pd.api.types.is_numeric_dtype(df["time"]):
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    else:
        df["time"] = pd.to_datetime(df["time"], utc=True)

    df = df.sort_values("time").reset_index(drop=True)

    # validate ไม่มีแถวซ้ำ
    dupes = df.duplicated(subset=["time"]).sum()
    if dupes > 0:
        logger.warning(f"พบ timestamp ซ้ำ {dupes} แถว — ตัดออก")
        df = df.drop_duplicates(subset=["time"]).reset_index(drop=True)

    # แนบ metadata
    df.attrs["symbol"] = symbol
    df.attrs["timeframe"] = timeframe
    df.attrs["fetched_at"] = datetime.now(timezone.utc).isoformat()

    return df


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    bars: int = 200,
    mcp_script: str = r"C:\Users\bobco\tradingview-mcp\index.js",
    settle_secs: float = 1.5,
) -> Optional[pd.DataFrame]:
    """
    ดึง OHLCV จาก TradingView ผ่าน MCP

    ขั้นตอน:
      1. เซ็ต symbol บน chart (tv_change_symbol)
      2. เซ็ต timeframe บน chart (tv_change_timeframe)
      3. รอ settle_secs ให้ chart โหลด
      4. ดึง OHLCV (tv_get_ohlcv)

    Parameters
    ----------
    symbol     : เช่น 'BTCUSDT', 'XAUUSD', 'NASDAQ:AAPL'
    timeframe  : เช่น '60' (1H), '240' (4H), 'D' (Daily)
    bars       : จำนวนแท่ง (max 500 ตามข้อจำกัด MCP)
    mcp_script : path ของ index.js
    settle_secs: เวลารอให้ chart โหลดหลังเปลี่ยน symbol/timeframe

    Returns
    -------
    pd.DataFrame คอลัมน์ time, open, high, low, close, volume
    หรือ None ถ้า bars ที่ได้น้อยกว่าที่ขอ (log เตือน แต่คืนเท่าที่ได้)

    Raises
    ------
    TVConnectionError : MCP ไม่ตอบ หรือ TradingView ไม่พร้อม
    TVDataError       : ได้ข้อมูลแต่ parse ไม่ได้
    ValueError        : bars เกิน 500
    """
    if bars > _MAX_BARS:
        raise ValueError(f"bars={bars} เกิน max {_MAX_BARS} ที่ MCP รองรับ")

    logger.info(f"fetch_ohlcv: {symbol} {timeframe} {bars} bars")

    # 1. เซ็ต symbol
    logger.debug(f"tv_change_symbol → {symbol}")
    _call_mcp_tool(_TOOL_CHANGE_SYMBOL, {"symbol": symbol}, mcp_script)

    # 2. เซ็ต timeframe
    logger.debug(f"tv_change_timeframe → {timeframe}")
    _call_mcp_tool(_TOOL_CHANGE_TIMEFRAME, {"timeframe": timeframe}, mcp_script)

    # 3. รอ chart โหลด
    logger.debug(f"รอ {settle_secs}s ให้ chart settle")
    time.sleep(settle_secs)

    # 4. ดึง OHLCV
    logger.debug(f"tv_get_ohlcv bars={bars}")
    result = _call_mcp_tool(_TOOL_GET_OHLCV, {"bars": bars}, mcp_script)

    if not result.get("ok"):
        raise TVConnectionError(
            f"tv_get_ohlcv คืน ok=false: {result}"
        )

    candles = result.get("candles", [])
    df = _parse_candles(candles, symbol, timeframe)

    # แจ้งถ้าได้น้อยกว่าที่ขอ
    if len(df) < bars:
        logger.warning(
            f"ขอ {bars} แท่ง แต่ได้ {len(df)} แท่ง "
            f"({symbol} {timeframe}) — คืนเท่าที่มี"
        )

    logger.info(
        f"fetch_ohlcv สำเร็จ: {symbol} {timeframe} "
        f"{len(df)} แท่ง "
        f"{df['time'].iloc[0]} → {df['time'].iloc[-1]} "
        f"fetched_at={df.attrs['fetched_at']}"
    )

    return df
