"""
Synapse — A Modular Community Operating System for Discord
============================================================
Captures community activity, drives engagement through configurable
economies and rules, and surfaces insights through a real-time dashboard.
Deploy it for any Discord-centric community — then configure it to match
your culture.

Package layout::

    synapse/
    ├── config.py          # YAML → typed Python config
    ├── database/
    │   ├── engine.py      # SQLAlchemy engine + async helper
    │   └── models.py      # All ORM models (12+ tables)
    ├── bot/
    │   ├── core.py        # Bot subclass, cog loader
    │   └── cogs/
    │       ├── social.py  # on_message event capture + reward pipeline
    │       ├── reactions.py  # Reaction tracking
    │       ├── voice.py   # Voice session tracking
    │       ├── threads.py # Thread creation tracking
    │       ├── meta.py    # /profile, /leaderboard, /preferences
    │       └── admin.py   # /award, /create-achievement, /grant-achievement
    ├── engine/
    │   ├── events.py      # SynapseEvent dataclass + base values
    │   ├── reward.py      # Reward calculation pipeline
    │   ├── achievements.py # Achievement check logic
    │   ├── quality.py     # Message quality modifiers
    │   ├── anti_gaming.py # Anti-gaming checks
    │   └── cache.py       # In-memory config cache + PG LISTEN/NOTIFY
    ├── services/
    │   ├── reward_service.py  # Event persistence + reward application
    │   ├── admin_service.py   # Audit-logged admin mutations
    │   └── seed.py            # Default data seeder
    └── api/
        ├── main.py        # FastAPI app
        ├── auth.py        # Discord OAuth2 → JWT
        └── routes/        # Public + admin REST endpoints
"""

__version__ = "0.1.0"
