"""Entry point: python main.py (Linux/Render deployment)."""
from __future__ import annotations

import asyncio
import logging
import sys
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from bot.app import TradingBot
from bot.config import load_config
from bot.log import setup_logging

# --- Fake Web Server for Render Free Tier ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass # Silence the logs so UptimeRobot pings don't spam your console

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()
# ---------------------------------------------

def main() -> int:
    cfg = load_config()
    setup_logging(cfg)
    log = logging.getLogger("main")
    log.info("Starting Asian Session Mean-Reversion Grid | %s | magic=%s", cfg.SYMBOL, cfg.MAGIC_NUMBER)
    
    # Start the background web server before starting the bot
    threading.Thread(target=run_web_server, daemon=True).start()
    log.info("Web server started on port %s", os.environ.get("PORT", 8080))

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