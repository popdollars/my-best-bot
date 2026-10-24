# Asian Session Mean-Reversion Micro-Grid (EURUSD M15, MetaTrader 5)

## Run (Windows only - the `MetaTrader5` package needs the desktop terminal)
1. Install Python 3.10+ and MetaTrader 5; log in to a **hedging DEMO** account; enable **Algo Trading**.
2. `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
3. `copy .env.example .env` and edit (Telegram token/chat id optional).
4. `python main.py`  (or F5 in VS Code -> "Run Asian Grid Bot"). Tests: `python -m unittest discover -s tests -v`.

## Layout
| File | Role |
|---|---|
| `bot/mt5_connector.py` | init, heartbeat, backoff reconnect, serialized MT5 thread |
| `bot/data_engine.py` + `indicators.py` | M15 candles, SMA20 / BB(20,2) / RSI14 on closed bars, 24h avg spread |
| `bot/strategy_engine.py` | entry crossing signals, 10-pip layering, group SL / TP maths (pure, tested) |
| `bot/execution_engine.py` | build/validate/send orders, SL+TP+magic+fill type, retries, partial fills, close-all |
| `bot/risk_manager.py` | session, spread, margin gates; kill-switch; trailing-DD lockout; persisted daily state |
| `bot/telegram_notifier.py` | non-blocking `requests.post` alerts |
| `bot/app.py` | orchestration: risk loop 500 ms, strategy loop 1 s, heartbeat loop 5 s |

## Rules as implemented
* Window 21:00-04:00 UTC (end exclusive); no Fri-evening/Sat/Sun-evening sessions. Existing baskets are managed outside the window; new grids and new legs are not opened.
* Max 3 positions, each exactly 0.01 lot, each leg 10 pips beyond the PRECEDING entry. No martingale.
* Unified TP = current SMA20 (re-synced each bar). `TP_BREAKEVEN_FLOOR=true` stops the TP from drifting below break-even; set false for the literal SMA.
* Every order carries SL + TP + magic + IOC/FOK. Legs 1-2 carry the projected group SL (anchor -/+ 30 pips); when leg 3 fills, SL is re-attached to all legs at (3rd actual fill -/+ 10 pips).
* Group SL hit -> flush all, pause `GROUP_SL_COOLDOWN_MIN`, write `logs/events.log`.
* Spread filter: block if spread > 1.5x 24h average (or > `MAX_SPREAD_PIPS`).
* Kill-switch: floating loss >= 5% of start-of-day balance -> close all, cancel pendings, urgent Telegram, lock to next 00:00 UTC.
* Trailing DD: basket floating loss OR (peak equity - equity) > 1.5% of start-of-day balance -> close all, lock to next 21:00 UTC.

## Important
* With $100 and 0.01 lot (~$0.10/pip) the 1.5% limit equals ~15 pips on one leg, so it fires before leg 3 / the group SL. The bot logs this at startup. Raise `TRAILING_DD_PCT` only if your prop rules allow it.
* Needs a **hedging** account (netting merges legs). Real accounts are refused unless `ALLOW_LIVE_TRADING=true`.
* Forward-test on demo for weeks. This strategy has small frequent wins and rare large losses; nothing here guarantees profit.
