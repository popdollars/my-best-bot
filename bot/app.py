"""TradingBot: Alpaca BTC/USD Version."""
from __future__ import annotations
import asyncio
import logging
import signal
import time

from .config import Config
from .data_engine import DataEngine
from .execution_engine import ExecutionEngine
from .models import Side
from .alpaca_connector import AlpacaConnector
from .risk_manager import RiskManager
from .strategy_engine import StrategyEngine
from .telegram_notifier import TelegramNotifier

log = logging.getLogger("bot.app")
events = logging.getLogger("events")

class TradingBot:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.notifier = TelegramNotifier(cfg)
        self.conn = AlpacaConnector(cfg, alert=self.notifier.notify)
        self.data = DataEngine(cfg, self.conn)
        self.strategy = StrategyEngine(cfg)
        self.exec = ExecutionEngine(cfg, self.conn)
        self.risk = RiskManager(cfg, self.conn, self.exec, self.notifier)
        self.exec.entries_allowed = lambda: not self.risk.locked()[0] and not self.risk.paused()[0]

        self._stop = asyncio.Event()
        self._tasks = []
        self._basket = {}
        self._closed_pnl = 0.0
        self._throttle = {}

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(seconds, 0.0))
        except asyncio.TimeoutError:
            pass

    def _install_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(self._stop.set))

    async def run(self) -> None:
        self._install_signals()
        try:
            if not await self._startup():
                return
            self._tasks = [
                asyncio.create_task(self._loop("heartbeat", self.cfg.HEARTBEAT_INTERVAL_SEC, self._heartbeat_step)),
                asyncio.create_task(self._loop("risk", self.cfg.RISK_INTERVAL_SEC, self._risk_step)),
                asyncio.create_task(self._loop("strategy", self.cfg.STRATEGY_INTERVAL_SEC, self._strategy_step)),
            ]
            await self._stop.wait()
        finally:
            await self._shutdown()

    async def _startup(self) -> bool:
        await self.notifier.start()
        attempt = 0
        while not self._stop.is_set():
            if await self.conn.connect():
                break
            attempt += 1
            await self._sleep(min(2 ** attempt, 60))
        if self._stop.is_set(): return False

        acct = await self.conn.account_info()
        if acct is None: return False

        await self.risk.initialize()
        self.notifier.notify(f"?? BTC Grid Bot ONLINE | Paper Balance: {acct.balance:.2f}")
        return True

    async def _shutdown(self) -> None:
        for t in self._tasks: t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.conn.shutdown()

    async def _loop(self, name: str, interval: float, step) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try: await step()
            except Exception: log.exception("Loop error")
            await self._sleep(interval - (time.monotonic() - started))

    async def _heartbeat_step(self) -> None:
        await self.conn.ensure_connected()

    async def _risk_step(self) -> None:
        if not self.conn.connected: return
        acct = await self.conn.account_info()
        positions = await self.conn.positions()
        if acct and positions is not None:
            await self.risk.evaluate_equity(acct, positions)

    async def _strategy_step(self) -> None:
        if not self.conn.connected: return
        positions = await self.conn.positions()
        tick = await self.conn.tick()
        info = await self.conn.symbol_info()
        if positions is None or tick is None or info is None: return
        
        # NOTE: You may need to adjust self.data.refresh to use Alpaca candle data!
        ind = await self.data.refresh(reference_time=int(time.time()))
        if ind is None: return
        
        signal_ = self.strategy.evaluate_entry(ind, tick)
        if not positions and signal_:
            # Place order
            res = await self.exec.open_position(signal_.side, self.cfg.BASE_LOT, 0, 0)
            if res.ok:
                self.notifier.notify(f"?? OPENED {signal_.side.value} at {res.price}")
        elif positions:
            # Manage / Close if needed based on your strategy logic
            pass
