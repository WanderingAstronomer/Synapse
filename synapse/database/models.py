"""
synapse.database.models — SQLAlchemy 2.0 Data Models
=====================================================

Complete schema implementation per 04_DATABASE_SCHEMA.md.

Tables (Phase 0 base + Phase 1 additions):

Core engagement loop
- users              — Community member profiles (Discord snowflake PK)
- user_stats         — Per-season engagement counters
- seasons            — Competitive windows
- activity_log       — Append-only event journal with idempotent insert
- event_lake         — Raw captured Discord events (immutable)
- event_counters     — Pre-computed O(1) context cache for the rule engine

Channel reward configuration
- channels           — Persistent Discord channel metadata
- channel_type_defaults — Server-wide reward multipliers per channel type
- channel_overrides  — Per-channel reward multiplier exceptions

Reward Firewall
- reward_rules       — Composable rules (JSONB predicates + outcomes)
- rule_snapshots     — Immutable versioned snapshots of published rulesets
- rule_evaluations   — Per-event trace: event → snapshot → matched rules → outcomes
- projection_checkpoints — Worker resume state for idempotent replay

Achievement system
- achievement_categories — Per-guild achievement category taxonomy
- achievement_rarities — Per-guild achievement rarity tiers
- achievement_series — Progression chains grouping achievement tiers
- achievement_templates — Admin-defined recognition with typed triggers
- user_achievements  — Earned badges

Media library
- media_files        — Uploaded images referenced by URL path
- media_folders      — Folder registry for organizing media assets
- svg_overlays       — Decorative frame registry (defaults + admin-uploadable)

Marketplace
- marketplace_items  — Admin-configured shop items (cosmetic-only)
- user_inventory     — One-way purchase records

User identity & auth
- user_profiles      — Discord identity cache (avatar, username, left_at)
- user_guild_roles   — Synced role membership for three-tier RBAC
- user_preferences   — Per-user notification opt-outs
- oauth_states       — CSRF-safe OAuth state tokens

Admin
- admin_log          — Append-only audit trail
- admin_rate_limit_events — Durable mutation events for admin throttling

Layout
- page_layouts       — Per-page layout configuration
- card_configs       — Per-card visual and content configuration
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
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
    """All event types that flow through the reward pipeline."""

    MESSAGE = "MESSAGE"
    REACTION_GIVEN = "REACTION_GIVEN"
    REACTION_RECEIVED = "REACTION_RECEIVED"
    THREAD_CREATE = "THREAD_CREATE"
    VOICE_TICK = "VOICE_TICK"
    MANUAL_AWARD = "MANUAL_AWARD"
    LEVEL_UP = "LEVEL_UP"
    ACHIEVEMENT_EARNED = "ACHIEVEMENT_EARNED"
    VOICE_JOIN = "VOICE_JOIN"
    VOICE_LEAVE = "VOICE_LEAVE"
    POLL_VOTE = "POLL_VOTE"


class ScalingCurve(enum.StrEnum):
    """Supported mathematical curves for reward scaling."""

    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"
    EXPONENTIAL = "exponential"
    STEP = "step"


class RulePriority(int, enum.Enum):
    """Priority levels for reward rules."""

    LOW = 10
    DEFAULT = 50
    HIGH = 100
    OVERRIDE = 1000


class TriggerType(enum.StrEnum):
    """Defines what condition causes an achievement to be checked."""

    STAT_THRESHOLD = "stat_threshold"
    XP_MILESTONE = "xp_milestone"
    LEVEL_REACHED = "level_reached"
    LEVEL_INTERVAL = "level_interval"
    EVENT_COUNT = "event_count"
    FIRST_EVENT = "first_event"
    MEMBER_TENURE = "member_tenure"
    INVITE_COUNT = "invite_count"
    MANUAL = "manual"


class AdminActionType(enum.StrEnum):
    """Categories of admin mutations recorded in admin_log."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SEASON_ROLL = "SEASON_ROLL"
    MANUAL_AWARD = "MANUAL_AWARD"
    MANUAL_REVOKE = "MANUAL_REVOKE"
    IMPORT = "IMPORT"


class MarketplaceItemType(enum.StrEnum):
    """Shop item categories supported by the cosmetic marketplace."""

    COSMETIC_BADGE = "COSMETIC_BADGE"
    DISCORD_ROLE = "DISCORD_ROLE"         # Formerly CUSTOM_ROLE_COLOR
    COSMETIC_OVERLAY = "COSMETIC_OVERLAY" # Formerly PROFILE_THEME
    TITLE = "TITLE"
    CONSUMABLE = "CONSUMABLE"


class SourceCategory(enum.StrEnum):
    """Origin of a captured event, used for audit and Rules Engine routing."""

    GATEWAY = "GATEWAY"  # Discord real-time gateway DISPATCH event
    REST = "REST"  # Discord REST API pull (scheduled or on-demand)
    SYNTHETIC = "SYNTHETIC"  # Internally generated (MANUAL_AWARD, LEVEL_UP, etc.)


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

    __table_args__ = (Index("ix_users_xp_desc", "xp"),)

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

    __table_args__ = (UniqueConstraint("guild_id", "name", name="uq_seasons_guild_name"),)

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
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    reactions_given: Mapped[int] = mapped_column(Integer, default=0)
    reactions_received: Mapped[int] = mapped_column(Integer, default=0)
    threads_created: Mapped[int] = mapped_column(Integer, default=0)
    voice_minutes: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="stats")

    def __repr__(self) -> str:
        return f"<UserStats user={self.user_id} season={self.season_id}>"


# ---------------------------------------------------------------------------
# Reward Firewall — Composable Rules
# ---------------------------------------------------------------------------
class RewardRule(Base):
    """
    Administratively defined 'Firewall Rule' for Discord interactions.
    Matches events via predicates and yields scaled outcomes.
    """

    __tablename__ = "reward_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)

    # List of atomic predicates: [{"field": "len", "op": ">=", "value": 100}, ...]
    predicates: Mapped[list] = mapped_column(JSONB, server_default="[]")

    # List of reward outcomes: [{"type": "xp", "base_value": 10, "scaling": {...}}, ...]
    outcomes: Mapped[list] = mapped_column(JSONB, server_default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_rules_guild_priority", "guild_id", "priority"),)


# ---------------------------------------------------------------------------
# Channels — persistent Discord channel metadata
# ---------------------------------------------------------------------------
class Channel(Base):
    """Stores Discord channel metadata synced from the guild snapshot.

    Provides persistent channel names, types, and parent category info so the
    dashboard can display rich channel information without the bot being online.
    """

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Discord snowflake
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # text, voice, forum, stage, announcement, category  # noqa: E501
    discord_category_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    discord_category_name: Mapped[str | None] = mapped_column(String(100), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_channels_guild_id", "guild_id"),)

    def __repr__(self) -> str:
        return f"<Channel id={self.id} name={self.name!r} type={self.type!r}>"


# ---------------------------------------------------------------------------
# ChannelTypeDefault — server-wide reward multipliers per channel type
# ---------------------------------------------------------------------------
class ChannelTypeDefault(Base):
    """Server-wide reward multipliers per channel type.

    Every channel inherits these defaults based on its type (text, voice,
    forum, stage, announcement).  Admins configure once per type.
    """

    __tablename__ = "channel_type_defaults"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    xp_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    
    __table_args__ = (
        UniqueConstraint(
            "guild_id",
            "channel_type",
            "event_type",
            name="uq_type_defaults_guild_type_event",
        ),
        Index("ix_type_defaults_guild", "guild_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChannelTypeDefault guild={self.guild_id} "
            f"type={self.channel_type!r} event={self.event_type!r}>"
        )


# ---------------------------------------------------------------------------
# ChannelOverride — per-channel reward multiplier exceptions
# ---------------------------------------------------------------------------
class ChannelOverride(Base):
    """Per-channel reward multiplier overrides.

    For specific channels that need different rules than their type default.
    Takes precedence over ChannelTypeDefault.
    """

    __tablename__ = "channel_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    xp_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        UniqueConstraint(
            "guild_id",
            "channel_id",
            "event_type",
            name="uq_overrides_guild_channel_event",
        ),
        Index("ix_overrides_channel", "channel_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChannelOverride guild={self.guild_id} "
            f"channel={self.channel_id} event={self.event_type!r}>"
        )


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
    source_system: Mapped[str] = mapped_column(String(30), nullable=False, default="discord")
    source_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    xp_delta: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rule_evaluation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("rule_evaluations.id", ondelete="SET NULL"), nullable=True
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
    )

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} user={self.user_id} type={self.event_type}>"


# ---------------------------------------------------------------------------
# AchievementCategory — per-guild achievement category taxonomy
# ---------------------------------------------------------------------------
class AchievementCategory(Base):
    __tablename__ = "achievement_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_achiev_categories_guild_name"),
    )

    def __repr__(self) -> str:
        return f"<AchievementCategory id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# AchievementRarity — per-guild achievement rarity tiers
# ---------------------------------------------------------------------------
class AchievementRarity(Base):
    __tablename__ = "achievement_rarities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#9e9e9e")
    emoji: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("guild_id", "name", name="uq_achiev_rarities_guild_name"),)

    def __repr__(self) -> str:
        return f"<AchievementRarity id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# AchievementSeries — progression chains grouping achievement tiers
# ---------------------------------------------------------------------------
class AchievementSeries(Base):
    __tablename__ = "achievement_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    tiers: Mapped[list[AchievementTemplate]] = relationship(
        back_populates="series", order_by="AchievementTemplate.series_order"
    )

    __table_args__ = (UniqueConstraint("guild_id", "name", name="uq_achiev_series_guild_name"),)

    def __repr__(self) -> str:
        return f"<AchievementSeries id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# AchievementTemplate — admin-defined recognition with typed triggers
# ---------------------------------------------------------------------------
class AchievementTemplate(Base):
    __tablename__ = "achievement_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # Category & rarity — FK to per-guild customisable tables
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("achievement_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    rarity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("achievement_rarities.id", ondelete="SET NULL"),
        nullable=True,
    )
    season_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("seasons.id", ondelete="SET NULL"),
        nullable=True,
    )
    overlay_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("svg_overlays.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Trigger system — replaces requirement_type/field/value/scope
    trigger_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=TriggerType.MANUAL.value,
    )
    trigger_config: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Series / progression
    series_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("achievement_series.id", ondelete="SET NULL"),
        nullable=True,
    )
    series_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Rewards
    xp_reward: Mapped[int] = mapped_column(Integer, default=0)
    gold_reward: Mapped[int] = mapped_column(Integer, default=0)

    # Badge image — URL or local path (data/badges/{guild_id}/filename)
    badge_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Controls
    announce_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    max_earners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    category: Mapped[AchievementCategory | None] = relationship()
    rarity: Mapped[AchievementRarity | None] = relationship()
    series: Mapped[AchievementSeries | None] = relationship(back_populates="tiers")
    season: Mapped[Season | None] = relationship()
    overlay: Mapped[SvgOverlay | None] = relationship()
    earned_by: Mapped[list[UserAchievement]] = relationship(back_populates="template")

    __table_args__ = (UniqueConstraint("guild_id", "name", name="uq_achiev_templates_guild_name"),)

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
        Integer,
        ForeignKey("achievement_templates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    granted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped[User] = relationship(back_populates="achievements")
    template: Mapped[AchievementTemplate] = relationship(back_populates="earned_by")

    def __repr__(self) -> str:
        return f"<UserAchievement user={self.user_id} achievement={self.achievement_id}>"


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
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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

    __table_args__ = (Index("ix_settings_category", "category"),)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} category={self.category!r}>"


# ---------------------------------------------------------------------------
# OAuthState — one-time CSRF tokens for OAuth callback validation
# ---------------------------------------------------------------------------
class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_oauth_states_created_at", "created_at"),)

    def __repr__(self) -> str:
        return f"<OAuthState state={self.state[:8]!r}...>"


# ---------------------------------------------------------------------------
# MediaFile — uploaded images for use across the system
# ---------------------------------------------------------------------------
class MediaFile(Base):
    """Uploaded image stored on disk, referenced by URL path.

    Provides a central media library so admins can upload images once
    and reference them from achievements, cards, or any future feature.
    """

    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(100), default=None)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(200), default=None)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_folders.id", ondelete="SET NULL"), nullable=True
    )

    folder: Mapped[MediaFolder | None] = relationship(
        back_populates="files", foreign_keys=[folder_id]
    )

    __table_args__ = (
        Index("ix_media_files_guild_id", "guild_id"),
        Index("ix_media_files_folder", "folder_id"),
    )

    def __repr__(self) -> str:
        return f"<MediaFile id={self.id} filename={self.filename!r}>"


# ---------------------------------------------------------------------------
# AdminRateLimitEvent — durable mutation events for admin throttling
# ---------------------------------------------------------------------------
class AdminRateLimitEvent(Base):
    __tablename__ = "admin_rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_admin_rate_limit_admin_ts", "admin_id", timestamp.desc()),
        Index("ix_admin_rate_limit_ts", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<AdminRateLimitEvent admin={self.admin_id!r} ts={self.timestamp}>"


# ---------------------------------------------------------------------------
# EventLake — append-only ephemeral event capture (P4)
# ---------------------------------------------------------------------------
class EventLake(Base):
    """Append-only table capturing ephemeral Discord gateway events.

    See 03B_DATA_LAKE.md §3B.3 for full schema rationale.
    Events are immutable once written.  Retention managed by periodic cleanup.
    """

    __tablename__ = "event_lake"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_event_lake_user_ts", "user_id", timestamp.desc()),
        Index("idx_event_lake_type_ts", "event_type", timestamp.desc()),
        Index("idx_event_lake_guild_ts", "guild_id", timestamp.desc()),
        Index(
            "idx_event_lake_channel_ts",
            "channel_id",
            timestamp.desc(),
            postgresql_where=channel_id.isnot(None),
        ),
        # Idempotency: prevent duplicate events from bot restarts / replays
        Index(
            "idx_event_lake_source",
            "source_id",
            unique=True,
            postgresql_where=source_id.isnot(None),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<EventLake id={self.id} type={self.event_type!r} "
            f"user={self.user_id} ts={self.timestamp}>"
        )


# ---------------------------------------------------------------------------
# EventCounter — pre-computed aggregation cache (P4)
# ---------------------------------------------------------------------------
class EventCounter(Base):
    """Pre-computed event counters for O(1) reads by the Rules Engine.

    See 03B_DATA_LAKE.md §3B.6 for design rationale.
    Updated transactionally with each Event Lake insert.
    """

    __tablename__ = "event_counters"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), primary_key=True)
    count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<EventCounter user={self.user_id} type={self.event_type!r} "
            f"period={self.period!r} count={self.count}>"
        )


# ---------------------------------------------------------------------------
# PageLayout — per-page layout configuration
# ---------------------------------------------------------------------------
class PageLayout(Base):
    """Stores the layout configuration for a dashboard page.

    Each page (dashboard, leaderboard, activity, achievements) gets a
    PageLayout row that holds the ordered list of cards and grid positions.
    The ``display_name`` is what appears in the sidebar navigation and can
    be customised by admins in edit mode.
    """

    __tablename__ = "page_layouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_slug: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    layout_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cards: Mapped[list[CardConfig]] = relationship(
        back_populates="page_layout",
        cascade="all, delete-orphan",
        order_by="CardConfig.position",
    )

    __table_args__ = (
        UniqueConstraint("guild_id", "page_slug", name="uq_page_layouts_guild_slug"),
    )

    def __repr__(self) -> str:
        return f"<PageLayout id={self.id} slug={self.page_slug!r}>"


# ---------------------------------------------------------------------------
# CardConfig — per-card visual and content configuration
# ---------------------------------------------------------------------------
class CardConfig(Base):
    """Per-card visual and content configuration within a page layout.

    Each card occupies a position in the parent page's grid layout.
    ``card_type`` determines the component rendered; ``config_json`` stores
    type-specific settings (background colour, image URL, icon, data source,
    stat selection, etc.).
    """

    __tablename__ = "card_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    page_layout_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("page_layouts.id", ondelete="CASCADE"), nullable=False
    )
    card_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grid_span: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)

    page_layout: Mapped[PageLayout] = relationship(back_populates="cards")

    __table_args__ = (Index("ix_card_configs_page_layout", "page_layout_id", "position"),)

    def __repr__(self) -> str:
        return f"<CardConfig id={self.id} type={self.card_type!r} pos={self.position}>"


# ---------------------------------------------------------------------------
# SvgOverlay — decorative frame/border registry
# ---------------------------------------------------------------------------
class SvgOverlay(Base):
    """Decorative frame/border registry.

    Ships with built-in defaults; admins can also upload custom SVGs.
    Composited client-side over achievement badge icons and marketplace items.
    """

    __tablename__ = "svg_overlays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    svg_url: Mapped[str] = mapped_column(String(500), nullable=False)
    preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_svg_overlays_guild_name"),
        Index("ix_svg_overlays_guild", "guild_id"),
    )

    def __repr__(self) -> str:
        return f"<SvgOverlay id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# MediaFolder — folder registry for organizing media library assets
# ---------------------------------------------------------------------------
class MediaFolder(Base):
    """Folder registry for organizing media library assets.

    Supports nested folders via a self-referential parent_id.
    """

    __tablename__ = "media_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    files: Mapped[list[MediaFile]] = relationship(
        back_populates="folder", foreign_keys="MediaFile.folder_id"
    )

    __table_args__ = (
        UniqueConstraint(
            "guild_id",
            "parent_id",
            "name",
            name="uq_media_folders_guild_parent_name",
        ),
        Index("ix_media_folders_guild", "guild_id"),
    )

    def __repr__(self) -> str:
        return f"<MediaFolder id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# RuleSnapshot — immutable versioned snapshots of published rulesets
# ---------------------------------------------------------------------------
class RuleSnapshot(Base):
    """Immutable versioned snapshot of the full active ruleset.

    Created each time an admin publishes a ruleset change. Used for
    deterministic replay and rule evaluation traceability.
    """

    __tablename__ = "rule_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    evaluations: Mapped[list[RuleEvaluation]] = relationship(back_populates="snapshot")

    __table_args__ = (
        UniqueConstraint("guild_id", "version", name="uq_rule_snapshots_guild_version"),
        Index("ix_rule_snapshots_guild_active", "guild_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<RuleSnapshot id={self.id} guild={self.guild_id} v={self.version}>"


# ---------------------------------------------------------------------------
# RuleEvaluation — per-event trace for audit and explainability
# ---------------------------------------------------------------------------
class RuleEvaluation(Base):
    """Per-event rule evaluation trace.

    Links captured event → applied rule snapshot → matched rules → outcomes.
    Powers the \"Why was I rewarded?\" explainability view.
    """

    __tablename__ = "rule_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_lake_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("event_lake.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("rule_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    # Matched rules, applied outcomes, and context captured at evaluation time
    matched_rules: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    outcomes_applied: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped[EventLake | None] = relationship()
    snapshot: Mapped[RuleSnapshot | None] = relationship(back_populates="evaluations")

    __table_args__ = (
        Index("ix_rule_evaluations_user", "user_id"),
        Index("ix_rule_evaluations_event", "event_lake_id"),
        Index("ix_rule_evaluations_snapshot", "snapshot_id"),
        Index("ix_rule_evaluations_guild_ts", "guild_id", "evaluated_at"),
        Index("ix_rule_evaluations_evaluated_at", "evaluated_at"),
    )

    def __repr__(self) -> str:
        return f"<RuleEvaluation id={self.id} event={self.event_lake_id}>"


# ---------------------------------------------------------------------------
# ProjectionCheckpoint — worker resume state for idempotent replay
# ---------------------------------------------------------------------------
class ProjectionCheckpoint(Base):
    """Projection worker resume state.

    Workers record their last successfully processed evaluation ID here so
    they resume correctly after a restart or failure without reprocessing.
    """

    __tablename__ = "projection_checkpoints"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_processed_evaluation_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectionCheckpoint worker={self.worker_id!r} "
            f"last={self.last_processed_evaluation_id}>"
        )


# ---------------------------------------------------------------------------
# UserProfile — Discord identity cache
# ---------------------------------------------------------------------------
class UserProfile(Base):
    """Discord identity cache for dashboard display and JWT population.

    Decouples the dashboard from real-time Discord API lookups.
    Retains anonymized profiles for members who have left the guild.

    Bot syncs on_message, on_member_join, and on_member_remove.
    On on_member_remove: set avatar_url = NULL, username = \"Former Member\",
    record left_at.
    """

    __tablename__ = "user_profiles"

    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list[UserGuildRole]] = relationship(
        back_populates="profile", foreign_keys="UserGuildRole.user_id"
    )

    __table_args__ = (Index("ix_user_profiles_guild", "guild_id"),)

    def __repr__(self) -> str:
        return f"<UserProfile discord_id={self.discord_id} username={self.username!r}>"


# ---------------------------------------------------------------------------
# UserGuildRole — synced Discord role membership for RBAC
# ---------------------------------------------------------------------------
class UserGuildRole(Base):
    """Synced Discord role membership for three-tier RBAC.

    Populated by the bot from on_member_update / periodic sync.
    JWT payload is built from these rows at session creation time.
    """

    __tablename__ = "user_guild_roles"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_profiles.discord_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    profile: Mapped[UserProfile] = relationship(back_populates="roles")

    __table_args__ = (Index("ix_user_guild_roles_guild", "guild_id"),)

    def __repr__(self) -> str:
        return f"<UserGuildRole user={self.user_id} role={self.role_id}>"


# ---------------------------------------------------------------------------
# MarketplaceItem — admin-configured shop item (cosmetic-only)
# ---------------------------------------------------------------------------
class MarketplaceItem(Base):
    """Admin-configured cosmetic shop item.

    Pricing is flexible: cost_xp and cost_gold are each optional.
    At least one must be non-null. If both are set, the member chooses
    which currency to spend at purchase time.

    Scope: cosmetic-only. No channel-access locks, no moderation capability.
    """

    __tablename__ = "marketplace_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=MarketplaceItemType.COSMETIC_BADGE.value,
    )
    cost_xp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_gold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rarity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("achievement_rarities.id", ondelete="SET NULL"), nullable=True
    )
    overlay_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("svg_overlays.id", ondelete="SET NULL"), nullable=True
    )
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # For CUSTOM_ROLE_COLOR: the Discord role assigned automatically on purchase
    discord_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    season_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional hard expiry — items cannot be purchased after this timestamp
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    rarity: Mapped[AchievementRarity | None] = relationship()
    overlay: Mapped[SvgOverlay | None] = relationship()
    purchases: Mapped[list[UserInventory]] = relationship(back_populates="item")

    __table_args__ = (Index("ix_marketplace_items_guild_active", "guild_id", "active"),)

    def __repr__(self) -> str:
        return f"<MarketplaceItem id={self.id} name={self.name!r} type={self.item_type!r}>"


# ---------------------------------------------------------------------------
# UserInventory — one-way purchase records
# ---------------------------------------------------------------------------
class UserInventory(Base):
    """One-way purchase record for marketplace items.

    Purchases are permanent: no refunds, no gifting, no trading.
    Role assignment for CUSTOM_ROLE_COLOR is handled by the bot.
    If bot role assignment fails, the record is preserved and the failure
    is logged for admin resolution.
    """

    __tablename__ = "user_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("marketplace_items.id", ondelete="CASCADE"), nullable=False
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped[MarketplaceItem] = relationship(back_populates="purchases")

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_inventory_user_item"),
        Index("ix_user_inventory_user", "user_id"),
        Index("ix_user_inventory_guild", "guild_id"),
    )

    def __repr__(self) -> str:
        return f"<UserInventory id={self.id} user={self.user_id} item={self.item_id}>"
