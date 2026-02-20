"""
synapse.services.rules_seeder — Default RewardRule Seeder
=========================================================

Idempotent seeder that creates one ``RewardRule`` per ``InteractionType``
that has non-zero base rewards (XP).  These rules establish
a baseline for the Rule Firewall.

Naming convention
-----------------
Seeded rules use the prefix ``"default:"`` in their ``name`` field, e.g.
``"default:MESSAGE"``.  This distinguishes auto-seeded rules from
admin-created rules and ensures the seeder can detect them on re-runs.

The seeder is idempotent: it only inserts rules whose ``name`` is not
already present for the given guild.  It never modifies or deletes
existing rules.

Calling convention
------------------
This is a synchronous function designed to be called via
``await run_db(seed_default_rules, engine, guild_id)`` from the bot's
``setup_hook`` (which has access to both the engine and the configured
``guild_id``).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from synapse.database.models import RewardRule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default rule definitions
# ---------------------------------------------------------------------------


def _build_default_rule_defs() -> list[dict]:
    """Build the list of default rule definitions.

    DEPRECATED: Default rules are now handled purely via the Rule Engine dashboard.
    Returns an empty list to prevent auto-seeding legacy rewards.
    """
    return []


# ---------------------------------------------------------------------------
# Public seeder function
# ---------------------------------------------------------------------------


def seed_default_rules(engine, guild_id: int) -> None:  # type: ignore[type-arg]
    """Upsert one default RewardRule per non-zero-reward InteractionType.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        The synchronous SQLAlchemy engine.
    guild_id : int
        The guild for which to seed rules.  Single-guild policy means this
        is always the primary guild from ``SynapseConfig.guild_id``.

    Notes
    -----
    Existing rules with names starting ``"default:"`` are never overwritten.
    This preserves admin edits to the default rules.
    """
    rule_defs = _build_default_rule_defs()

    with Session(engine) as session:
        # Load names of already-seeded default rules for this guild
        existing_names: set[str] = set(
            session.scalars(
                select(RewardRule.name).where(
                    RewardRule.guild_id == guild_id,
                    RewardRule.name.like("default:%"),
                )
            ).all()
        )

        inserted = 0
        for rule_def in rule_defs:
            if rule_def["name"] in existing_names:
                continue

            session.add(
                RewardRule(
                    guild_id=guild_id,
                    name=rule_def["name"],
                    priority=rule_def["priority"],
                    predicates=rule_def["predicates"],
                    outcomes=rule_def["outcomes"],
                    is_active=True,
                )
            )
            inserted += 1

        if inserted:
            session.commit()
            logger.info(
                "Seeded %d default reward rules for guild %d.",
                inserted,
                guild_id,
            )
        else:
            logger.debug("Default reward rules already present for guild %d.", guild_id)
