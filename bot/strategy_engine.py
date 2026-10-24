"""StrategyEngine: pure signal + grid/basket maths (no MT5 calls -> fully unit-testable)."""
from __future__ import annotations

import logging
import statistics

from .models import Indicators, Side, Signal

log = logging.getLogger("bot.strategy")


class StrategyEngine:
    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._prev_ask: float | None = None
        self._prev_bid: float | None = None
        self._consumed_bar: int | None = None

    # ------------------------------------------------------------------ entry signal
    def evaluate_entry(self, ind: Indicators, tick) -> Signal | None:
        """Call EVERY loop (it tracks the previous tick so 'crosses' are real crossings).

        SELL: Ask crosses above Upper BB AND RSI > 70.
        BUY : Bid crosses below Lower BB AND RSI < 30.
        One signal per M15 bar (call mark_consumed after a successful entry)."""
        prev_ask, prev_bid = self._prev_ask, self._prev_bid
        self._prev_ask, self._prev_bid = tick.ask, tick.bid
        if prev_ask is None or prev_bid is None:
            return None
        if self._consumed_bar == ind.bar_time:
            return None
        if prev_ask <= ind.upper < tick.ask and ind.rsi > self._cfg.RSI_OVERBOUGHT:
            return Signal(Side.SELL, tick.bid,
                          f"Ask {tick.ask:.5f} crossed UpperBB {ind.upper:.5f}, RSI {ind.rsi:.1f}")
        if prev_bid >= ind.lower > tick.bid and ind.rsi < self._cfg.RSI_OVERSOLD:
            return Signal(Side.BUY, tick.ask,
                          f"Bid {tick.bid:.5f} crossed LowerBB {ind.lower:.5f}, RSI {ind.rsi:.1f}")
        return None

    def mark_consumed(self, bar_time: int) -> None:
        self._consumed_bar = bar_time

    # ------------------------------------------------------------------ basket helpers
    @staticmethod
    def basket_side(positions) -> tuple[Side | None, bool]:
        """(side, mixed). mixed=True means BUY and SELL coexist (should never happen)."""
        if not positions:
            return None, False
        sides = {Side.from_position_type(p.type) for p in positions}
        if len(sides) > 1:
            return None, True
        return next(iter(sides)), False

    def should_layer(self, side: Side, positions, tick, pip: float) -> bool:
        """Add the next 0.01 lot exactly GRID_STEP_PIPS beyond the PRECEDING entry (max 3 total)."""
        if not positions or len(positions) >= self._cfg.MAX_POSITIONS:
            return False
        last_entry = positions[-1].price_open  # positions are ordered oldest -> newest
        step = self._cfg.GRID_STEP_PIPS * pip
        eps = pip * 0.01
        if side.is_buy:
            return tick.ask <= last_entry - step + eps
        return tick.bid >= last_entry + step - eps

    def provisional_sl(self, side: Side, anchor_price: float, pip: float) -> float:
        """SL used before the 3rd leg exists: where the group SL WILL sit if all legs fill at
        exact spacing: anchor -/+ ((MAX-1)*STEP + BUFFER) pips. Guarantees every order carries an SL."""
        dist = ((self._cfg.MAX_POSITIONS - 1) * self._cfg.GRID_STEP_PIPS + self._cfg.GROUP_SL_BUFFER_PIPS) * pip
        return anchor_price - dist if side.is_buy else anchor_price + dist

    def group_sl(self, side: Side, positions, pip: float) -> float:
        """Once the 3rd position is open: exactly GROUP_SL_BUFFER_PIPS beyond the 3rd entry's
        ACTUAL execution price. Before that: the provisional level (same for all legs)."""
        if len(positions) >= self._cfg.MAX_POSITIONS:
            ref = positions[self._cfg.MAX_POSITIONS - 1].price_open
            dist = self._cfg.GROUP_SL_BUFFER_PIPS * pip
            return ref - dist if side.is_buy else ref + dist
        return self.provisional_sl(side, positions[0].price_open, pip)

    def group_tp(self, side: Side, entry_prices: list[float], ind: Indicators, pip: float) -> float:
        """Unified TP = current 20-SMA. If TP_BREAKEVEN_FLOOR, never worse than basket
        average entry + TP_MIN_PROFIT_PIPS (the SMA can drift past a stale entry)."""
        tp = ind.sma
        if self._cfg.TP_BREAKEVEN_FLOOR and entry_prices:
            avg = statistics.fmean(entry_prices)
            margin = self._cfg.TP_MIN_PROFIT_PIPS * pip
            tp = max(tp, avg + margin) if side.is_buy else min(tp, avg - margin)
        return tp

    @staticmethod
    def software_exit(side: Side, tick, tp: float, sl: float) -> str | None:
        """Backstop in case broker-side SL/TP modification failed or was skipped."""
        if side.is_buy:
            if tick.bid <= sl:
                return "GROUP_SL"
            if tick.bid >= tp:
                return "GROUP_TP"
        else:
            if tick.ask >= sl:
                return "GROUP_SL"
            if tick.ask <= tp:
                return "GROUP_TP"
        return None
