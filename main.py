"""Entry point:  python main.py   (Windows + MetaTrader 5 terminal required)."""
from __future__ import annotations

import asyncio
import logging
import sys

from bot.app import TradingBot
from bot.config import load_config
from bot.log import setup_logging


def main() -> int:
    cfg = load_config()
    setup_logging(cfg)
    log = logging.getLogger("main")
    log.info("Starting Asian Session Mean-Reversion Grid | %s | magic=%s", cfg.SYMBOL, cfg.MAGIC_NUMBER)
    try:
        asyncio.run(TradingBot(cfg).run())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception:  # noqa: BLE001
        log.critical("Fatal error", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
