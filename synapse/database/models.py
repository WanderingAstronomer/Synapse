"""
synapse.database.models — SQLAlchemy 2.0 Data Models
=====================================================

Complete schema implementation per 04_DATABASE_SCHEMA.md.

Tables:
- users              — Club member profiles (Discord snowflake PK)
- user_stats         — Per-season engagement counters
- seasons            — Competitive windows
- activity_log       — Append-only event journal with idempotent insert
- zones              — Channel groupings
- zone_channels      — Zone <> Channel mapping
- zone_multipliers   — Per-zone, per-event-type weights
- achievement_templates — Admin-defined recognition
- user_achievements  — Earned badges
- quests             — Gamified tasks
- admin_log          — Append-only audit trail
- user_preferences   — Per-user notification opt-outs
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Shared base for all Synapse ORM models."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class InteractionType(enum.StrEnum):
    """All event types that flow through the reward engine."""
    MESSAGE = "MESSAGE"
    REACTION_GIVEN = "REACTION_GIVEN"
    REACTION_RECEIVED = "REACTION_RECEIVED"
    THREAD_CREATE = "THREAD_CREATE"
    VOICE_TICK = "VOICE_TICK"
    QUEST_COMPLETE = "QUEST_COMPLETE"
    MANUAL_AWARD = "MANUAL_AWARD"
    LEVEL_UP = "LEVEL_UP"
    ACHIEVEMENT_EARNED = "ACHIEVEMENT_EARNED"
    VOICE_JOIN = "VOICE_JOIN"
    VOICE_LEAVE = "VOICE_LEAVE"


class QuestStatus(enum.StrEnum):
    """Lifecycle states for a Quest."""
    OPEN = "open"
    CLAIMED = "claimed"
    COMPLETE = "complete"


class AdminActionType(enum.StrEnum):
    """Categories of admin mutations recorded in admin_log."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SEASON_ROLL = "SEASON_ROLL"
    MANUAL_AWARD = "MANUAL_AWARD"
    MANUAL_REVOKE = "MANUAL_REVOKE"
    IMPORT = "IMPORT"


# ---------------------------------------------------------------------------
# Users — one row per Discord member
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    discord_name: Mapped[str] = mapped_column(String(100), nullable=False)
    discord_avatar_hash: Mapped[str | None] = mapped_column(String(100), default=None)
    github_username: Mapped[str | None] = mapped_column(String(39), default=None)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    gold: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stats: Mapped[list[UserStats]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list[ActivityLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    achievements: Mapped[list[UserAchievement]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    preferences: Mapped[UserPreferences | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_xp_desc", "xp"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.discord_name!r} lvl={self.level}>"


# ---------------------------------------------------------------------------
# Seasons — competitive windows
# ---------------------------------------------------------------------------
class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_seasons_guild_name"),
    )

    def __repr__(self) -> str:
        return f"<Season id={self.id} name={self.name!r} active={self.active}>"


# ---------------------------------------------------------------------------
# UserStats — per-season engagement counters
# ---------------------------------------------------------------------------
class UserStats(Base):
    __tablename__ = "user_stats"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    season_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="CASCADE"), primary_key=True
    )
    season_stars: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_stars: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    reactions_given: Mapped[int] = mapped_column(Integer, default=0)
    reactions_received: Mapped[int] = mapped_column(Integer, default=0)
    threads_created: Mapped[int] = mapped_column(Integer, default=0)
    voice_minutes: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="stats")

    def __repr__(self) -> str:
        return f"<UserStats user={self.user_id} season={self.season_id}>"


# ---------------------------------------------------------------------------
# Zones — channel groupings
# ---------------------------------------------------------------------------
class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    channels: Mapped[list[ZoneChannel]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )
    multipliers: Mapped[list[ZoneMultiplier]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_zones_guild_name"),
    )

    def __repr__(self) -> str:
        return f"<Zone id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# ZoneChannels — zone <> channel mapping
# ---------------------------------------------------------------------------
class ZoneChannel(Base):
    __tablename__ = "zone_channels"

    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    zone: Mapped[Zone] = relationship(back_populates="channels")

    __table_args__ = (
        Index("ix_zone_channels_channel_id", "channel_id"),
    )

    def __repr__(self) -> str:
        return f"<ZoneChannel zone={self.zone_id} channel={self.channel_id}>"


# ---------------------------------------------------------------------------
# ZoneMultipliers — per-zone, per-event-type weights
# ---------------------------------------------------------------------------
class ZoneMultiplier(Base):
    __tablename__ = "zone_multipliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), nullable=False
    )
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    xp_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    star_multiplier: Mapped[float] = mapped_column(Float, default=1.0)

    zone: Mapped[Zone] = relationship(back_populates="multipliers")

    __table_args__ = (
        UniqueConstraint("zone_id", "interaction_type", name="uq_zone_mult_zone_type"),
    )

    def __repr__(self) -> str:
        return f"<ZoneMultiplier zone={self.zone_id} type={self.interaction_type}>"


# ---------------------------------------------------------------------------
# ActivityLog — append-only event journal
# ---------------------------------------------------------------------------
class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    season_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True
    )
    zone_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="SET NULL"), nullable=True
    )
    source_system: Mapped[str] = mapped_column(
        String(30), nullable=False, default="discord"
    )
    source_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    xp_delta: Mapped[int] = mapped_column(Integer, default=0)
    star_delta: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="activity_logs")

    __table_args__ = (
        # Partial unique index for idempotent insert (D04-07)
        Index(
            "ix_activity_log_idempotent",
            "source_system",
            "source_event_id",
            unique=True,
            postgresql_where=source_event_id.isnot(None),
        ),
        Index("ix_activity_log_user_time", "user_id", "timestamp"),
        Index("ix_activity_log_timestamp", "timestamp"),
        Index("ix_activity_log_event_time", "event_type", "timestamp"),
        Index("ix_activity_log_zone_time", "zone_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} user={self.user_id} type={self.event_type}>"


# ---------------------------------------------------------------------------
# AchievementTemplate — admin-defined recognition
# ---------------------------------------------------------------------------
class AchievementTemplate(Base):
    __tablename__ = "achievement_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="social")
    requirement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    requirement_scope: Mapped[str] = mapped_column(String(20), default="season")
    requirement_field: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requirement_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0)
    gold_reward: Mapped[int] = mapped_column(Integer, default=0)
    badge_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rarity: Mapped[str] = mapped_column(String(20), default="common")
    announce_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    earned_by: Mapped[list[UserAchievement]] = relationship(back_populates="template")

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_achiev_templates_guild_name"),
    )

    def __repr__(self) -> str:
        return f"<AchievementTemplate id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# UserAchievement — earned badges
# ---------------------------------------------------------------------------
class UserAchievement(Base):
    __tablename__ = "user_achievements"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    achievement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("achievement_templates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    granted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped[User] = relationship(back_populates="achievements")
    template: Mapped[AchievementTemplate] = relationship(back_populates="earned_by")

    def __repr__(self) -> str:
        return f"<UserAchievement user={self.user_id} achievement={self.achievement_id}>"


# ---------------------------------------------------------------------------
# Quest — gamified tasks
# ---------------------------------------------------------------------------
class Quest(Base):
    __tablename__ = "quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    xp_reward: Mapped[int] = mapped_column(Integer, default=50)
    gold_reward: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[QuestStatus] = mapped_column(
        Enum(QuestStatus, name="quest_status_enum"), default=QuestStatus.OPEN
    )
    github_issue_url: Mapped[str | None] = mapped_column(String(500), default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Quest id={self.id} title={self.title!r}>"


# ---------------------------------------------------------------------------
# AdminLog — append-only audit trail
# ---------------------------------------------------------------------------
class AdminLog(Base):
    __tablename__ = "admin_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_table: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    before_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_admin_log_actor_time", "actor_id", "timestamp"),
        Index("ix_admin_log_target", "target_table", "target_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<AdminLog id={self.id} actor={self.actor_id} action={self.action_type}>"


# ---------------------------------------------------------------------------
# UserPreferences — per-user notification opt-outs
# ---------------------------------------------------------------------------
class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    announce_level_up: Mapped[bool] = mapped_column(Boolean, default=True)
    announce_achievements: Mapped[bool] = mapped_column(Boolean, default=True)
    announce_awards: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="preferences")

    def __repr__(self) -> str:
        return f"<UserPreferences user={self.user_id}>"


# ---------------------------------------------------------------------------
# Setting — admin-configurable key-value store
# ---------------------------------------------------------------------------
class Setting(Base):
    """Key-value configuration store.

    Every gameplay tuning knob (base XP, anti-gaming thresholds, quality
    modifiers, etc.) lives here so admins can adjust values from the
    dashboard without redeploying.  Values are stored as JSON strings;
    typed accessors live in :class:`~synapse.engine.cache.ConfigCache`.
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_settings_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} category={self.category!r}>"
