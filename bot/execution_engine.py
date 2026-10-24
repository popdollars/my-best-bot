"""ExecutionEngine: Handles orders via Alpaca."""
from __future__ import annotations
import asyncio
import logging
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from .models import OrderResult, Side

log = logging.getLogger("bot.exec")

class ExecutionEngine:
    def __init__(self, cfg, connector) -> None:
        self._cfg = cfg
        self._conn = connector
        self._lock = asyncio.Lock()
        self._frozen = False
        self.entries_allowed = lambda: True

    async def open_position(self, side: Side, volume: float, sl: float, tp: float, comment: str | None = None) -> OrderResult:
        if self._frozen or not self.entries_allowed():
            return OrderResult(False, message="entries blocked")
        async with self._lock:
            order_side = OrderSide.BUY if side.is_buy else OrderSide.SELL
            req = MarketOrderRequest(
                symbol=self._cfg.SYMBOL,
                qty=round(volume, 6),
                side=order_side,
                time_in_force=TimeInForce.GTC
            )
            res = await self._conn.call(self._conn.trading_client.submit_order, order_data=req)
            if res:
                log.info(f"Order OK {side.value} {volume} @ {res.filled_avg_price}")
                return OrderResult(True, ticket=res.id, price=float(res.filled_avg_price or 0.0), volume=float(res.qty))
            return OrderResult(False, message="Alpaca order failed")

    async def modify_sltp(self, positions, sl: float, tp: float | None) -> bool:
        # Alpaca handles SL/TP via software in this bot's logic
        return True

    async def close_all(self, reason: str) -> bool:
        self._frozen = True
        try:
            async with self._lock:
                res = await self._conn.call(self._conn.trading_client.close_all_positions, cancel_orders=True)
                if res is not None:
                    log.info(f"Closed all positions: {reason}")
                    return True
                return False
        finally:
            self._frozen = False

    async def cancel_pending(self) -> int:
        return 0
