from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from synapse.database.models import (
    Base,
    Channel,
    ChannelOverride,
    ChannelTypeDefault,
    InteractionType,
    Setting,
)
from synapse.engine.cache import ConfigCache


@pytest.fixture
def db_engine():
    # Use in-memory SQLite with StaticPool to share connection across threads/sessions
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(db_engine) -> Generator[Session, None, None]:
    with Session(db_engine) as session:
        yield session


class TestConfigCacheSettings:
    def test_load_settings(self, session: Session, db_engine):
        # Insert settings before cache init
        session.add(Setting(key="int_val", value_json="42"))
        session.add(Setting(key="bool_val", value_json="true"))
        session.add(Setting(key="str_val", value_json='"hello"'))
        session.add(Setting(key="dict_val", value_json='{"a": 1}'))
        session.commit()

        c = ConfigCache(db_engine)
        c.load_all()

        assert c.get_int("int_val") == 42
        assert c.get_bool("bool_val") is True
        assert c.get_setting("str_val") == "hello"
        assert c.get_setting("dict_val") == {"a": 1}
        assert c.get_int("missing", 99) == 99

    def test_reload_settings(self, session: Session, db_engine):
        session.add(Setting(key="val", value_json="10"))
        session.commit()

        c = ConfigCache(db_engine)
        c.load_all()
        assert c.get_int("val") == 10

        # Update in DB
        s = session.scalar(select(Setting).where(Setting.key == "val"))
        if s:
            s.value_json = "20"
        session.commit()

        # Simulate NOTIFY
        c.handle_notify("settings")
        assert c.get_int("val") == 20


class TestConfigCacheMultipliers:
    def test_resolve_with_defaults(self, db_engine):
        c = ConfigCache(db_engine)
        c.load_all()
        assert c.resolve_multipliers(123, InteractionType.MESSAGE) == (1.0, 1.0)

    def test_resolve_exact_override(self, session: Session, db_engine):
        session.add(
            ChannelOverride(
                channel_id=100,
                guild_id=1,
                event_type=InteractionType.MESSAGE,
                xp_multiplier=2.0,
                star_multiplier=3.0,
            )
        )
        session.commit()

        c = ConfigCache(db_engine)
        c.load_all()

        assert c.resolve_multipliers(100, InteractionType.MESSAGE) == (2.0, 3.0)
        # Verify specific overrides don't affect other events
        assert c.resolve_multipliers(100, InteractionType.REACTION_GIVEN) == (1.0, 1.0)

    def test_resolve_wildcard_override(self, session: Session, db_engine):
        session.add(
            ChannelOverride(
                channel_id=100, guild_id=1, event_type="*", xp_multiplier=5.0, star_multiplier=5.0
            )
        )
        session.commit()

        c = ConfigCache(db_engine)
        c.load_all()

        assert c.resolve_multipliers(100, InteractionType.MESSAGE) == (5.0, 5.0)
        assert c.resolve_multipliers(100, InteractionType.REACTION_GIVEN) == (5.0, 5.0)

    def test_resolve_type_defaults(self, session: Session, db_engine):
        # Register channel info
        session.add(Channel(id=200, guild_id=1, type="text", name="general"))
        # Add type default for 'text' channels in guild 1
        session.add(
            ChannelTypeDefault(
                guild_id=1,
                channel_type="text",
                event_type=InteractionType.MESSAGE,
                xp_multiplier=10.0,
                star_multiplier=1.0,
            )
        )
        session.commit()

        c = ConfigCache(db_engine)
        c.load_all()

        assert c.resolve_multipliers(200, InteractionType.MESSAGE) == (10.0, 1.0)
        # Different type/event shouldn't match
        assert c.resolve_multipliers(200, InteractionType.REACTION_GIVEN) == (1.0, 1.0)

    def test_precedence_rules(self, session: Session, db_engine):
        # 1. Override > 2. Wildcard Override > 3. Type Default > 4. Wildcard Type > 5. Global

        session.add(Channel(id=300, guild_id=1, type="voice", name="voice-lounge"))

        # Add all levels
        session.add(
            ChannelOverride(
                channel_id=300,
                guild_id=1,
                event_type=InteractionType.MESSAGE,
                xp_multiplier=2.0,
                star_multiplier=2.0,
            )
        )
        session.add(
            ChannelOverride(
                channel_id=300, guild_id=1, event_type="*", xp_multiplier=3.0, star_multiplier=3.0
            )
        )
        session.add(
            ChannelTypeDefault(
                guild_id=1,
                channel_type="voice",
                event_type=InteractionType.MESSAGE,
                xp_multiplier=4.0,
                star_multiplier=4.0,
            )
        )
        session.add(
            ChannelTypeDefault(
                guild_id=1,
                channel_type="voice",
                event_type="*",
                xp_multiplier=5.0,
                star_multiplier=5.0,
            )
        )
        session.commit()

        c = ConfigCache(db_engine)
        c.load_all()

        # Should match #1 (Exact Override)
        assert c.resolve_multipliers(300, InteractionType.MESSAGE) == (2.0, 2.0)

        # Remove #1
        ov = session.scalar(
            select(ChannelOverride).where(ChannelOverride.event_type == InteractionType.MESSAGE)
        )
        session.delete(ov)
        session.commit()
        c.handle_notify("channel_overrides")

        # Should match #2 (Wildcard Override)
        assert c.resolve_multipliers(300, InteractionType.MESSAGE) == (3.0, 3.0)

        # Remove #2
        ov_wild = session.scalar(select(ChannelOverride).where(ChannelOverride.event_type == "*"))
        session.delete(ov_wild)
        session.commit()
        c.handle_notify("channel_overrides")

        # Should match #3 (Type Default)
        assert c.resolve_multipliers(300, InteractionType.MESSAGE) == (4.0, 4.0)

        # Remove #3
        td = session.scalar(
            select(ChannelTypeDefault).where(
                ChannelTypeDefault.event_type == InteractionType.MESSAGE
            )
        )
        session.delete(td)
        session.commit()
        c.handle_notify("channel_type_defaults")

        # Should match #4 (Type Wildcard)
        assert c.resolve_multipliers(300, InteractionType.MESSAGE) == (5.0, 5.0)

        # Remove #4
        td_wild = session.scalar(
            select(ChannelTypeDefault).where(ChannelTypeDefault.event_type == "*")
        )
        session.delete(td_wild)
        session.commit()
        c.handle_notify("channel_type_defaults")

        # Should match #5 (Global Default)
        assert c.resolve_multipliers(300, InteractionType.MESSAGE) == (1.0, 1.0)
