"""Logging: console + rotating files (bot.log for everything, events.log for critical events)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(cfg) -> None:
    Path(cfg.LOG_DIR).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO))
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    main_file = RotatingFileHandler(Path(cfg.LOG_DIR) / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    main_file.setFormatter(fmt)
    root.addHandler(main_file)

    events = logging.getLogger("events")  # propagates to root as well
    ev_file = RotatingFileHandler(Path(cfg.LOG_DIR) / "events.log", maxBytes=2_000_000, backupCount=10, encoding="utf-8")
    ev_file.setFormatter(fmt)
    events.addHandler(ev_file)
