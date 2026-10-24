"""DataEngine: Fetches M15 history via Alpaca Crypto API."""
from __future__ import annotations
import logging
import time
import datetime
import numpy as np
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from .indicators import bollinger, rsi_wilder
from .models import Indicators

log = logging.getLogger("bot.data")
BAR_SECONDS = 15 * 60

class DataEngine:
    def __init__(self, cfg, connector) -> None:
        self._cfg = cfg
        self._conn = connector
        self._cached = None
        self._last_fetch = 0.0

    @property
    def last(self):
        return self._cached

    async def fetch_rates(self, count: int | None = None):
        count = count or self._cfg.CANDLES_TO_FETCH
        try:
            start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15 * (count + 10))
            req = CryptoBarsRequest(
                symbol_or_symbols=self._cfg.SYMBOL,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute), # FIXED HERE
                start=start_time
            )
            bars = await self._conn.call(self._conn.crypto_client.get_crypto_bars, req)
            if not bars or self._cfg.SYMBOL not in bars.data:
                log.error("Alpaca returned no data for %s", self._cfg.SYMBOL)
                return None
            
            df = bars.df
            df = df.tail(count)
            
            dtype = [('time', 'i8'), ('close', 'f8'), ('spread', 'f8')]
            result = np.zeros(len(df), dtype=dtype)
            result['time'] = df['timestamp'].astype('int64') // 10**9
            result['close'] = df['close']
            result['spread'] = 10.0
            return result
        except Exception as e:
            log.error("Error fetching Alpaca bars: %s", e)
            return None

    @staticmethod
    def compute(rates, cfg) -> Indicators | None:
        closed = rates[:-1]
        min_bars = max(cfg.SMA_PERIOD, cfg.RSI_PERIOD * 3) + 1
        if len(closed) < min_bars:
            return None
        closes = closed["close"].astype(float)
        sma, upper, lower = bollinger(closes, cfg.SMA_PERIOD, cfg.BB_STD)
        rsi = rsi_wilder(closes, cfg.RSI_PERIOD)
        spreads = closed["spread"][-cfg.SPREAD_LOOKBACK_BARS:].astype(float)
        avg_spread = float(np.mean(spreads)) if len(spreads) else 0.0
        values = (sma, upper, lower, rsi, avg_spread)
        if not all(np.isfinite(v) for v in values):
            return None
        return Indicators(bar_time=int(closed["time"][-1]), close=float(closes[-1]), sma=sma,
                          upper=upper, lower=lower, rsi=rsi, avg_spread_points=avg_spread)

    async def refresh(self, reference_time: int | None = None, force: bool = False) -> Indicators | None:
        now = time.monotonic()
        if not force and self._cached and now - self._last_fetch < self._cfg.DATA_REFRESH_SEC:
            return self._stale_check(self._cached, reference_time)
        rates = await self.fetch_rates()
        if rates is None:
            return None
        ind = self.compute(rates, self._cfg)
        if ind is None:
            return None
        self._cached, self._last_fetch = ind, now
        return self._stale_check(ind, reference_time)

    def _stale_check(self, ind: Indicators, reference_time: int | None) -> Indicators | None:
        if reference_time is not None and reference_time - ind.bar_time > 3 * BAR_SECONDS:
            return None
        return ind
