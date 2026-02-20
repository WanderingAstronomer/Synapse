from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine

# JSONB -> TEXT shim for SQLite test
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from synapse.database.models import Base, User, UserProfile
from synapse.services.profile_service import anonymize_on_leave


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine

def test_anonymize_on_leave_clears_global_user(db_engine):
    """
    Verify that anonymize_on_leave updates BOTH UserProfile (per-guild)
    AND User (global) tables to remove PII.
    """
    user_id = 999
    guild_id = 101

    # 1. Setup: Create a User and UserProfile
    with Session(db_engine) as s:
        user = User(
            id=user_id,
            discord_name="Real Name",
            discord_avatar_hash="hash123"
        )
        profile = UserProfile(
            discord_id=user_id,
            guild_id=guild_id,
            username="Real Name",
            avatar_url="http://cdn/hash123",
            last_seen=datetime.now(),
            left_at=None
        )
        s.add(user)
        s.add(profile)
        s.commit()

    # 2. Act: Call anonymize_on_leave
    anonymize_on_leave(db_engine, user_id, guild_id)

    # 3. Assert: Check both tables
    with Session(db_engine) as s:
        # Check Profile (was already working)
        p = s.get(UserProfile, user_id)
        assert p.username == "Former Member"
        assert p.avatar_url is None
        assert p.left_at is not None

        # Check Global User (THE FIX)
        u = s.get(User, user_id)
        assert u.discord_name == "Former Member"
        assert u.discord_avatar_hash is None

