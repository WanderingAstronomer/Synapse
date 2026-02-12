"""
synapse.config — YAML Configuration Loader
===========================================

**Why this file exists:**
This module reads ``config.yaml`` for **infrastructure-only** settings
(Discord identity, DB tuning, admin role, etc.).  All gameplay tuning
values (XP, anti-gaming, quality modifiers, economy) now live in the
``settings`` database table, editable from the Admin dashboard.

Usage::

    from synapse.config import load_config

    cfg = load_config()          # reads ./config.yaml by default
    print(cfg.community_name)    # "Synapse Dev"
    print(cfg.guild_id)          # 1468816181854081229
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Typed settings object — infrastructure/identity only.
# Gameplay tuning lives in the DB ``settings`` table.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SynapseConfig:
    """Immutable configuration loaded from ``config.yaml``.

    Contains only infrastructure and identity settings.
    All gameplay tuning (XP, anti-gaming, quality, economy) is in the
    ``settings`` DB table and accessed via :class:`ConfigCache`.
    """

    # Identity
    community_name: str
    community_motto: str

    # Discord
    bot_prefix: str
    guild_id: int  # Primary guild snowflake (for seeding & scoping)

    # Dashboard
    dashboard_port: int

    # Admin / Hardened Access
    admin_role_id: int  # Discord role required for admin commands/dashboard

    # Optional
    announce_channel_id: int | None = None  # Where to post level-ups / achievements


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_config(path: str | Path = "config.yaml") -> SynapseConfig:
    """Read *path* and return a :class:`SynapseConfig` instance.

    Parameters
    ----------
    path:
        Filesystem path to the YAML configuration file.
        Defaults to ``config.yaml`` in the current working directory.

    Raises
    ------
    FileNotFoundError
        If the YAML file doesn't exist.
    KeyError
        If a required key is missing from the YAML file.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path.resolve()}\n"
            "Hint: copy config.yaml.example → config.yaml and edit it."
        )

    with open(config_path, encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh)

    return SynapseConfig(
        community_name=raw["community_name"],
        community_motto=raw["community_motto"],
        bot_prefix=raw["bot_prefix"],
        guild_id=int(raw["guild_id"]),
        dashboard_port=int(raw["dashboard_port"]),
        admin_role_id=int(raw["admin_role_id"]),
        announce_channel_id=(
            int(raw["announce_channel_id"]) if raw.get("announce_channel_id") else None
        ),
    )
