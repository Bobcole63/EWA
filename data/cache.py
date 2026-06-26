"""
EWA — Data Layer: OHLCV Cache
==============================
Cache DataFrame ต่อ (symbol, timeframe) เพื่อลด MCP call ซ้ำ
มี TTL ต่อ timeframe — กันใช้ data เก่าโดยไม่รู้ตัว

ทุกครั้งที่คืน cache จะแนบ fetched_at เดิม ให้รู้ว่า data เก่าแค่ไหน
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)

# TTL default ต่อ timeframe (วินาที)
DEFAULT_TTL: dict[str, int] = {
    "1":   60,      # 1m  → cache 1 นาที
    "5":   180,     # 5m  → cache 3 นาที
    "15":  300,     # 15m → cache 5 นาที
    "60":  300,     # 1H  → cache 5 นาที
    "240": 600,     # 4H  → cache 10 นาที
    "D":   1800,    # Daily → cache 30 นาที
    "W":   3600,    # Weekly → cache 1 ชั่วโมง
}
DEFAULT_TTL_FALLBACK = 300  # timeframe ที่ไม่อยู่ใน dict → 5 นาที


@dataclass
class _CacheEntry:
    df: pd.DataFrame
    fetched_at: datetime
    symbol: str
    timeframe: str


class OHLCVCache:
    """
    In-memory cache สำหรับ OHLCV DataFrame

    ใช้งาน:
        cache = OHLCVCache()
        df = cache.get("BTCUSDT", "60")       # None ถ้า miss/หมดอายุ
        cache.set("BTCUSDT", "60", df)
    """

    def __init__(self, ttl_override: Optional[dict[str, int]] = None):
        """
        Parameters
        ----------
        ttl_override : dict ของ {timeframe: seconds} สำหรับ override TTL default
        """
        self._store: dict[str, _CacheEntry] = {}
        self._ttl = {**DEFAULT_TTL, **(ttl_override or {})}

    def _key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol.upper()}_{timeframe}"

    def _ttl_secs(self, timeframe: str) -> int:
        return self._ttl.get(timeframe, DEFAULT_TTL_FALLBACK)

    def get(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        คืน DataFrame ถ้า cache hit และยังไม่หมดอายุ
        คืน None ถ้า cache miss หรือหมดอายุ (log ให้รู้)

        Parameters
        ----------
        symbol    : เช่น 'BTCUSDT'
        timeframe : เช่น '60'

        Returns
        -------
        pd.DataFrame พร้อม attrs[fetched_at] เดิม หรือ None
        """
        key = self._key(symbol, timeframe)
        entry = self._store.get(key)

        if entry is None:
            logger.debug(f"cache miss: {key}")
            return None

        age_secs = (datetime.now(timezone.utc) - entry.fetched_at).total_seconds()
        ttl = self._ttl_secs(timeframe)

        if age_secs > ttl:
            logger.info(
                f"cache expired: {key} "
                f"(อายุ {age_secs:.0f}s > TTL {ttl}s) → fetch ใหม่"
            )
            del self._store[key]
            return None

        logger.debug(
            f"cache hit: {key} "
            f"fetched_at={entry.fetched_at.isoformat()} "
            f"อายุ {age_secs:.0f}s"
        )
        # คืน copy พร้อม metadata เดิม
        df = entry.df.copy()
        df.attrs["fetched_at"] = entry.fetched_at.isoformat()
        df.attrs["symbol"] = entry.symbol
        df.attrs["timeframe"] = entry.timeframe
        df.attrs["from_cache"] = True
        return df

    def set(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        """
        เก็บ DataFrame ลง cache

        Parameters
        ----------
        symbol    : เช่น 'BTCUSDT'
        timeframe : เช่น '60'
        df        : DataFrame ที่ได้จาก fetch_ohlcv (ต้องมี attrs[fetched_at])

        Returns
        -------
        None
        """
        key = self._key(symbol, timeframe)
        fetched_at_str = df.attrs.get("fetched_at")

        if fetched_at_str:
            fetched_at = datetime.fromisoformat(fetched_at_str)
        else:
            fetched_at = datetime.now(timezone.utc)
            logger.warning(f"df ไม่มี attrs[fetched_at] — ใช้เวลาปัจจุบันแทน")

        self._store[key] = _CacheEntry(
            df=df.copy(),
            fetched_at=fetched_at,
            symbol=symbol.upper(),
            timeframe=timeframe,
        )
        logger.debug(f"cache set: {key} ({len(df)} แถว)")

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """
        ล้าง cache สำหรับ symbol+timeframe นั้น

        Parameters
        ----------
        symbol    : เช่น 'BTCUSDT'
        timeframe : เช่น '60'
        """
        key = self._key(symbol, timeframe)
        if key in self._store:
            del self._store[key]
            logger.info(f"cache invalidated: {key}")

    def clear_all(self) -> None:
        """ล้าง cache ทั้งหมด"""
        self._store.clear()
        logger.info("cache cleared all")

    def status(self) -> list[dict]:
        """
        คืน list สรุปสถานะ cache ทุก entry
        ใช้ debug / log ได้

        Returns
        -------
        list of dict: {key, symbol, timeframe, bars, fetched_at, age_secs, ttl, expired}
        """
        now = datetime.now(timezone.utc)
        result = []
        for key, entry in self._store.items():
            age = (now - entry.fetched_at).total_seconds()
            ttl = self._ttl_secs(entry.timeframe)
            result.append({
                "key": key,
                "symbol": entry.symbol,
                "timeframe": entry.timeframe,
                "bars": len(entry.df),
                "fetched_at": entry.fetched_at.isoformat(),
                "age_secs": round(age, 1),
                "ttl_secs": ttl,
                "expired": age > ttl,
            })
        return result


# singleton สำหรับใช้ทั่วโปรเจค
_default_cache = OHLCVCache()


def get_cache() -> OHLCVCache:
    """คืน singleton cache instance"""
    return _default_cache
