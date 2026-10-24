"""Pure helpers (time windows, pip maths, rounding)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def pip_size(point: float, digits: int) -> float:
    """1 pip = 10 points on 3/5-digit symbols, else 1 point."""
    return point * 10 if digits in (3, 5) else point


def next_utc_hour(now: datetime, hour: int) -> datetime:
    """Next occurrence (strictly after `now`) of HH:00:00 UTC."""
    candidate = now.astimezone(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def in_trading_window(now: datetime, start_hour: int, end_hour: int, skip_weekend: bool = True) -> bool:
    """True inside [start_hour, end_hour) UTC; handles windows that wrap midnight.

    With skip_weekend: no Friday-evening / Saturday / Sunday-evening sessions
    (thin liquidity, gaps, closed market).
    """
    now = now.astimezone(timezone.utc)
    h, wd = now.hour, now.weekday()  # Mon=0 ... Sun=6
    if start_hour > end_hour:
        evening, morning = h >= start_hour, h < end_hour
        if not (evening or morning):
            return False
    else:
        if not (start_hour <= h < end_hour):
            return False
        evening, morning = False, True
    if skip_weekend:
        if evening and wd in (4, 5, 6):
            return False
        if morning and wd in (5, 6):
            return False
    return True


def normalize_volume(volume: float, vmin: float, vmax: float, vstep: float) -> float:
    if vstep <= 0:
        vstep = vmin if vmin > 0 else 0.01
    steps = math.floor(volume / vstep + 1e-9)
    v = max(vmin, min(vmax, steps * vstep))
    return round(v, 8)
