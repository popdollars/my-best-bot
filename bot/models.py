"""Plain data containers."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def is_buy(self) -> bool:
        return self is Side.BUY

@dataclass(frozen=True)
class Indicators:
    bar_time: int
    close: float
    sma: float
    upper: float
    lower: float
    rsi: float
    avg_spread_points: float

@dataclass(frozen=True)
class Signal:
    side: Side
    price: float
    reason: str

@dataclass(frozen=True)
class OrderResult:
    ok: bool
    retcode: int | None = None
    ticket: int | None = None
    price: float = 0.0
    volume: float = 0.0
    message: str = ""
    partial: bool = False
