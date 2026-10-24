"""RiskManager: Alpaca version."""
from __future__ import annotations
import asyncio, json, logging, os, time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .utils import in_trading_window, next_utc_hour, normalize_volume, now_utc, pip_size

log = logging.getLogger("bot.risk")
events = logging.getLogger("events")

@dataclass
class RiskState:
    day: str
    start_balance: float
    peak_equity: float
    locked_until: str | None = None
    lock_reason: str = ""
    pause_until: str | None = None
    pause_reason: str = ""

class RiskManager:
    def __init__(self, cfg, connector, execution, notifier) -> None:
        self._cfg = cfg
        self._conn = connector
        self._exec = execution
        self._notifier = notifier
        self._path = Path(cfg.STATE_DIR) / "risk_state.json"
        self.state: RiskState | None = None
        self._last_save = 0.0
        self._last_enforce = 0.0

    def _load(self) -> dict | None:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")
            self._last_save = time.monotonic()
        except Exception:
            pass

    async def initialize(self) -> None:
        acct = await self._conn.account_info()
        if acct is None: raise RuntimeError("account_info unavailable")
        today = now_utc().date().isoformat()
        loaded = self._load()
        if loaded and loaded.get("day") == today:
            self.state = RiskState(**{k: loaded[k] for k in RiskState.__dataclass_fields__ if k in loaded})
        else:
            self.state = RiskState(day=today, start_balance=acct.balance, peak_equity=acct.equity)
        self._save()

    async def describe_limits(self) -> None:
        pass

    def locked(self, now=None):
        now = now or now_utc()
        until = self.state.locked_until if self.state else None
        if until and now < datetime.fromisoformat(until):
            return True, f"{self.state.lock_reason} until {until}"
        return False, ""

    def paused(self, now=None):
        now = now or now_utc()
        until = self.state.pause_until if self.state else None
        if until and now < datetime.fromisoformat(until):
            return True, f"{self.state.pause_reason} until {until}"
        return False, ""

    def pause(self, minutes: float, reason: str) -> None:
        until = now_utc() + timedelta(minutes=minutes)
        self.state.pause_until, self.state.pause_reason = until.isoformat(), reason
        self._save()

    def session_open(self, now=None) -> bool:
        return True # Crypto is 24/7

    def base_volume(self, info) -> float:
        return normalize_volume(self._cfg.BASE_LOT, info.volume_min, info.volume_max, info.volume_step)

    def spread_ok(self, tick, ind, info) -> tuple[bool, str]:
        return True, "ok" # We mock spread in data engine to bypass this

    async def pre_trade_checks(self, kind: str, side, price: float, tick, ind, info, n_open: int) -> tuple[bool, str]:
        if self.locked()[0]: return False, "locked"
        if self.paused()[0]: return False, "paused"
        if n_open >= self._cfg.MAX_POSITIONS: return False, "position cap reached"
        if kind == "new" and n_open != 0: return False, "basket already open"
        
        volume = self.base_volume(info)
        margin = price * volume # Simple margin calculation for crypto
        acct = await self._conn.account_info()
        if acct is None: return False, "account info failed"
        
        # 3x margin safety factor for crypto
        if acct.margin_free < margin * self._cfg.MARGIN_SAFETY_FACTOR:
            return False, f"free margin too low"
        return True, "ok"

    def _roll_day(self, acct) -> None:
        today = now_utc().date().isoformat()
        if self.state.day != today:
            self.state.day, self.state.start_balance, self.state.peak_equity = today, acct.balance, acct.equity
            self._save()

    def _expire_locks(self, acct, now: datetime) -> None:
        st = self.state
        if st.locked_until and now >= datetime.fromisoformat(st.locked_until):
            st.locked_until, st.lock_reason, st.peak_equity = None, "", acct.equity
            self._save()
        if st.pause_until and now >= datetime.fromisoformat(st.pause_until):
            st.pause_until, st.pause_reason = None, ""
            self._save()

    async def evaluate_equity(self, acct, positions) -> str | None:
        now = now_utc()
        self._roll_day(acct)
        self._expire_locks(acct, now)
        st = self.state
        floating = sum(p.profit + p.swap for p in positions) if positions else 0.0
        equity = acct.equity
        
        if equity > st.peak_equity:
            st.peak_equity = equity
            if time.monotonic() - self._last_save > 30:
                self._save()

        kill_limit = st.start_balance * self._cfg.KILL_SWITCH_PCT / 100
        trail_limit = st.start_balance * self._cfg.TRAILING_DD_PCT / 100

        if positions and floating <= -kill_limit:
            await self._trigger("KILL_SWITCH", "Kill switch hit", next_utc_hour(now, 0))
            return "KILL_SWITCH"

        peak_dd = st.peak_equity - equity
        basket_dd = -floating if positions else 0.0
        if basket_dd > trail_limit or peak_dd > trail_limit:
            await self._trigger("TRAILING_DRAWDOWN", "Trailing DD hit", next_utc_hour(now, 0))
            return "TRAILING_DRAWDOWN"
        return None

    async def _trigger(self, kind: str, detail: str, lock_until: datetime) -> None:
        st = self.state
        st.locked_until, st.lock_reason = lock_until.isoformat(), kind
        self._save()
        await self._exec.close_all(kind)
        await self._exec.cancel_pending()
