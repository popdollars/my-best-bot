"""TelegramNotifier: plain `requests.post` to the Bot API, never blocks the trading loop."""
from __future__ import annotations
import asyncio
import logging
import queue
import threading
import time
from datetime import datetime, timezone
import requests

log = logging.getLogger("bot.telegram")

# FIXED: Uses {token} so it can be formatted securely from environment variables
API_URL = "https://api.telegram.org/bot{token}/sendMessage"
_SENTINEL = object()

class TelegramNotifier:
    def __init__(self, cfg) -> None:
        self._token = cfg.TELEGRAM_TOKEN
        self._chat_id = cfg.TELEGRAM_CHAT_ID
        self.enabled = bool(self._token and self._chat_id)
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._worker: threading.Thread | None = None
        self._session = requests.Session()
        if not self.enabled:
            log.warning("Telegram disabled (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set) - alerts go to log only")

    async def start(self) -> None:
        if self.enabled and self._worker is None:
            self._worker = threading.Thread(target=self._run, name="telegram", daemon=True)
            self._worker.start()
            log.info("Telegram notifier started")

    async def stop(self) -> None:
        if self._worker is None:
            return
        try:
            self._queue.put_nowait(_SENTINEL)
        except queue.Full:
            pass
        await asyncio.to_thread(self._worker.join, 5.0)
        self._worker = None

    def notify(self, text: str) -> None:
        log.info("TG> %s", text.replace("\n", " | "))
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(text)
            except (queue.Empty, queue.Full):
                log.error("Telegram queue overflow; message dropped")

    def send_urgent(self, text: str) -> bool:
        log.critical("TG-URGENT> %s", text.replace("\n", " | "))
        if not self.enabled:
            return False
        return self._post(text, attempts=5)

    async def send_async(self, text: str, urgent: bool = False) -> bool:
        if urgent:
            return await asyncio.to_thread(self.send_urgent, text)
        self.notify(text)
        return True

    def notify_entry(self, side: str, symbol: str, volume: float, price: float, sl: float, tp: float,
                     level: int, max_levels: int, rsi: float) -> None:
        self.notify(
            f"📈 ENTRY {side} {symbol}\n"
            f"Lot: {volume} | Grid level: {level}/{max_levels}\n"
            f"Price: {price:.5f}\nSL: {sl:.5f} | TP (SMA): {tp:.5f}\nRSI: {rsi:.1f}"
        )

    def notify_heartbeat(self, balance: float, equity: float, floating: float, open_positions: int,
                         spread_pips: float, status: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.notify(
            f"💓 HEARTBEAT {ts}\n"
            f"Balance: {balance:.2f} | Equity: {equity:.2f}\n"
            f"Floating P/L: {floating:+.2f} | Open: {open_positions}\n"
            f"Spread: {spread_pips:.1f} pips | Status: {status}"
        )

    def notify_circuit_breaker(self, kind: str, detail: str, lock_until: str) -> bool:
        return self.send_urgent(
            f"🚨🚨 CIRCUIT BREAKER: {kind} 🚨🚨\n{detail}\n"
            f"All positions closed. Trading LOCKED until {lock_until}."
        )

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            try:
                self._post(item, attempts=3)
            except Exception:
                log.exception("Telegram worker error")

    def _post(self, text: str, attempts: int = 3) -> bool:
        url = API_URL.format(token=self._token)
        payload = {"chat_id": self._chat_id, "text": text[:4000], "disable_web_page_preview": True}
        for attempt in range(1, attempts + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return True
                if resp.status_code == 429:
                    try:
                        wait = float(resp.json().get("parameters", {}).get("retry_after", 2))
                    except (ValueError, AttributeError):
                        wait = 2.0
                    log.warning("Telegram rate-limited, waiting %.0fs", wait)
                    time.sleep(min(wait, 30))
                    continue
                log.error("Telegram HTTP %s: %s", resp.status_code, resp.text[:200])
                if 400 <= resp.status_code < 500:
                    return False
            except requests.RequestException as exc:
                log.warning("Telegram attempt %d/%d failed: %s", attempt, attempts, exc)
            time.sleep(min(2 ** attempt, 15))
        log.error("Telegram message undeliverable after %d attempts", attempts)
        return False
