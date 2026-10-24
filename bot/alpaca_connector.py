"""AlpacaConnector: Pure BTC/USD setup."""
from __future__ import annotations
import asyncio, functools, logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import PositionSide
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoLatestQuoteRequest

log = logging.getLogger("bot.connector")

class MockAccount:
    def __init__(self, acc):
        self.login = acc.account_number
        self.server = "Alpaca_Paper"
        self.balance = float(acc.cash)
        self.equity = float(acc.equity)
        self.margin_free = float(acc.buying_power)
        self.leverage = 1
        self.margin_mode = 0
        self.trade_mode = 0
        self.trade_allowed = True

class MockTick:
    def __init__(self, bid, ask): self.bid, self.ask = bid, ask

class MockPosition:
    def __init__(self, pos):
        self.ticket = pos.asset_id
        self.symbol = pos.symbol
        self.volume = float(pos.qty)
        self.price_open = float(pos.avg_entry_price)
        self.magic = 0
        self.type = 0 if pos.side == PositionSide.LONG else 1
        self.profit = float(pos.unrealized_pl)
        self.swap = 0.0

class MockSymbolInfo:
    def __init__(self):
        self.volume_min = 0.0001
        self.volume_max = 100.0
        self.volume_step = 0.0001
        self.point = 1.0 # 1 point = .00 for BTC
        self.digits = 2
        self.trade_tick_size = 1.0
        self.trade_tick_value = 1.0
        self.trade_stops_level = 0

class AlpacaConnector:
    def __init__(self, cfg, alert: Callable[[str], None] | None = None) -> None:
        self._cfg = cfg
        self._pool = ThreadPoolExecutor(max_workers=1)
        self.connected = False
        self.symbol = "BTC/USD" 
        self.trading_client = None
        self.crypto_client = None

    async def call(self, fn: Callable[..., Any], *args: Any, call_timeout: float = 10.0, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        try:
            fut = loop.run_in_executor(self._pool, functools.partial(fn, *args, **kwargs))
            return await asyncio.wait_for(fut, call_timeout)
        except Exception as e:
            log.error(f"Alpaca error: {e}")
            return None

    async def connect(self) -> bool:
        try:
            self.trading_client = TradingClient(self._cfg.ALPACA_API_KEY, self._cfg.ALPACA_SECRET_KEY, paper=True)
            self.crypto_client = CryptoHistoricalDataClient()
            acc = await self.call(self.trading_client.get_account)
            if acc:
                self.connected = True
                return True
            return False
        except Exception:
            return False

    async def is_healthy(self) -> bool:
        return self.connected

    async def ensure_connected(self) -> bool:
        if not self.connected:
            return await self.connect()
        return True

    async def shutdown(self) -> None:
        self._pool.shutdown(wait=False)

    async def account_info(self):
        acc = await self.call(self.trading_client.get_account)
        return MockAccount(acc) if acc else None

    async def symbol_info(self):
        return MockSymbolInfo()

    async def tick(self):
        req = CryptoLatestQuoteRequest(symbol_or_symbols=self.symbol)
        quote = await self.call(self.crypto_client.get_crypto_latest_quote, req)
        if quote and self.symbol in quote:
            return MockTick(quote[self.symbol].bid_price, quote[self.symbol].ask_price)
        return None

    async def positions(self) -> list | None:
        res = await self.call(self.trading_client.get_all_positions)
        return [MockPosition(p) for p in res if p.symbol == self.symbol] if res is not None else None
