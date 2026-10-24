"""Vectorised indicators (numpy only)."""
from __future__ import annotations

import numpy as np


def sma(closes: np.ndarray, period: int) -> float:
    return float(np.mean(closes[-period:]))


def bollinger(closes: np.ndarray, period: int, n_std: float) -> tuple[float, float, float]:
    """Returns (sma, upper, lower) using population std (ddof=0), the platform standard."""
    window = np.asarray(closes[-period:], dtype=float)
    mid = float(window.mean())
    sd = float(window.std(ddof=0))
    return mid, mid + n_std * sd, mid - n_std * sd


def rsi_wilder(closes: np.ndarray, period: int = 14) -> float:
    """Wilder-smoothed RSI of the last value. Needs > period closes."""
    closes = np.asarray(closes, dtype=float)
    if len(closes) <= period:
        raise ValueError("not enough data for RSI")
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))
