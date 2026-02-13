"""
synapse.bot.__main__ — Entry point for ``python -m synapse.bot``
================================================================

Wiring:
1. Load .env (secrets).
2. Load config.yaml (soft settings).
3. Create the SQLAlchemy engine and ensure tables exist.
4. Build and warm the ConfigCache (in-memory config from DB).
5. Start the PG LISTEN/NOTIFY background listener.
6. Create the SynapseBot and hand it config + engine + cache.
7. Start the bot (blocking — runs the asyncio event loop).

First-run initialisation (zones, channels, settings) is handled by the
admin dashboard setup wizard, not by startup seed files.

Run with::

    uv run python -m synapse.bot
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from synapse.bot.core import SynapseBot
from synapse.config import load_config
from synapse.database.engine import create_db_engine, init_db
from synapse.engine.cache import ConfigCache
from synapse.services.log_buffer import install_handler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("synapse")

# Capture all logs into the in-memory ring buffer for the admin log viewer
install_handler()


def main() -> None:
    """Bootstrap and run the Synapse bot."""

    # 1. Environment variables (secrets).
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "your-discord-bot-token-here":
        logger.critical(
            "DISCORD_TOKEN is not set.  "
            "Copy .env.example → .env and paste your bot token."
        )
        sys.exit(1)

    # 2. Soft configuration.
    cfg = load_config()
    logger.info("Config loaded — Community: %s", cfg.community_name)

    # 3. Database.
    engine = create_db_engine()
    init_db(engine)

    # 4. Build and warm the ConfigCache.
    cache = ConfigCache(engine)

    # 5. Start PG LISTEN/NOTIFY background thread.
    cache.start_listener()

    # 6. Bot.
    bot = SynapseBot(cfg=cfg, engine=engine, cache=cache)

    # 7. Run (blocks until Ctrl+C or SIGTERM).
    logger.info("Starting Synapse bot…")
    try:
        bot.run(token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully…")


if __name__ == "__main__":
    main()
