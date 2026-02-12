"""
synapse.bot.__main__ — Entry point for ``python -m synapse.bot``
================================================================

Wiring:
1. Load .env (secrets).
2. Load config.yaml (soft settings).
3. Create the SQLAlchemy engine and ensure tables exist.
4. Build and warm the ConfigCache (in-memory config from DB).
5. Seed default data if needed.
6. Start the PG LISTEN/NOTIFY background listener.
7. Create the SynapseBot and hand it config + engine + cache.
8. Start the bot (blocking — runs the asyncio event loop).

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
from synapse.services.seed import seed_database

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("synapse")


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
    logger.info("Config loaded — Club: %s", cfg.club_name)

    # 3. Database.
    engine = create_db_engine()
    init_db(engine)

    # 4. Seed default zones, achievements, and season (idempotent).
    if cfg.guild_id:
        seed_database(engine, cfg.guild_id)

    # 5. Build and warm the ConfigCache.
    cache = ConfigCache(engine)

    # 6. Start PG LISTEN/NOTIFY background thread.
    cache.start_listener()

    # 7. Bot.
    bot = SynapseBot(cfg=cfg, engine=engine, cache=cache)

    # 8. Run (blocks until Ctrl+C or SIGTERM).
    logger.info("Starting Synapse bot…")
    try:
        bot.run(token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully…")


if __name__ == "__main__":
    main()
