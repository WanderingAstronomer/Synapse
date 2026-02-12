# Changelog

All notable changes to Project Synapse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-12

### 🎉 Initial Release

Project Synapse 1.0 is a production-ready gamified engagement framework for university clubs, transforming Discord activity into meaningful recognition through XP, Stars, Gold, achievements, and seasonal progression.

### Added

#### Core Systems
- **Dual Economy**: XP for progression, Stars for social recognition, Gold for rewards
- **Zone-Based Multipliers**: Per-channel grouping with customizable XP and Star multipliers for each event type
- **Intelligent Reward Engine**: Quality-weighted message XP based on length, code blocks, links, and attachments
- **Seasonal Stats**: Separate lifetime and seasonal tracking with automatic season rollover
- **Achievement System**: 4 trigger types (counter_threshold, star_threshold, xp_milestone, custom) with 11 seed achievements

#### Bot Features (discord.py)
- **Social Activity Tracking**: Message XP with quality modifiers, reply bonuses, and thread participation
- **Reaction System**: Star rewards with unique-reactor weighting and diminishing returns
- **Voice Channel XP**: Activity-based rewards with anti-idle detection
- **Thread Creation Tracking**: Rewards for initiating discussions
- **User Commands**:
  - `/profile [member]` — View XP, level, gold, stars, achievements, and rank
  - `/leaderboard [xp|stars]` — Top members by XP or Stars
  - `/link-github <username>` — Associate GitHub account (ready for GitHub Neural Bridge)
  - `/preferences <setting> <on|off>` — Toggle announcement preferences
  - `/buy-coffee` — Gold sink demonstration
- **Admin Commands**:
  - `/award <member> [xp] [gold] [reason]` — Manual XP/Gold awards
  - `/create-achievement` — Define new achievement templates
  - `/grant-achievement <member> <id>` — Grant achievements manually
  - `/season <name> [days]` — Create new seasons

#### Anti-Gaming Measures
- Self-reaction filtering
- Unique-reactor weighting for Star awards
- Per-user per-target reaction caps
- Diminishing returns on repeated interactions
- Reaction velocity limits
- Message quality thresholds

#### API (FastAPI)
- **Public Endpoints**:
  - Live metrics (total members, XP, active users, top level)
  - Paginated leaderboards (XP, Gold, Level)
  - Daily activity charts with event-type breakdown
  - Achievement browsing with rarity and category filters
  - User profile lookup by Discord ID
- **Admin Endpoints** (JWT-protected):
  - Zone CRUD with channel mapping and multiplier management
  - Achievement builder with full field editing
  - Award distribution (XP, Gold, achievements)
  - Settings management with category filtering
  - Audit log with before/after JSON snapshots
- **Authentication**: Discord OAuth2 → JWT issuance with admin role verification
- **Rate Limiting**: 30 mutations/minute per admin session

#### Dashboard (SvelteKit + Tailwind + Chart.js)
- **Club Pulse (Public)**:
  - Hero banner with live metrics and animated counters
  - Multi-tab leaderboard (XP, Gold, Level) with Discord avatars and progress bars
  - Interactive Chart.js stacked bar chart showing daily event breakdown
  - Filterable event feed with event-type color coding
  - Achievement showcase with rarity glow effects and category/rarity filters
  - Recent achievers display with Discord avatar integration
- **Admin Panel** (OAuth-gated):
  - Zone editor with drag-and-drop channel assignment
  - Achievement builder with live preview
  - Bulk award distribution with user search
  - Inline settings editor with bulk save
  - Expandable audit log with JSON diff viewer
  - Real-time validation and error handling
  - Flash notification system
- **Full Responsive Design**: Mobile-optimized with Tailwind CSS
- **Discord CDN Integration**: Automatic avatar URL construction with fallback handling

#### Database (PostgreSQL 16)
- **12 Tables**: Users, Events, SeasonalStats, Achievements, UserAchievements, Zones, ZoneChannels, ZoneMultipliers, Seasons, Settings, AuditLog, Quests
- **Advanced Features**:
  - JSONB columns for flexible event metadata and audit snapshots
  - Partial indexes for performance optimization
  - PG LISTEN/NOTIFY for cache invalidation (no Redis needed)
  - Composite indexes for efficient leaderboard queries
  - Idempotent event insertion (ON CONFLICT DO NOTHING)

#### Configuration & Infrastructure
- YAML-based configuration (`config.yaml`) for club-specific settings
- Environment variable support (`.env` with `.env.example` template)
- Docker Compose orchestration (4 services: db, bot, api, dashboard)
- Seed data system for achievements, settings, and zones
- Comprehensive test suite with pytest
- Multi-stage Docker builds for production optimization

#### Developer Experience
- Type-safe API client in TypeScript
- SQLAlchemy 2.0 with Mapped[] annotations
- uv for fast Python dependency management
- Hot-reload support for both bot and API
- VS Code task definitions for common operations
- Structured logging throughout the stack

### Technical Highlights
- **Idempotent Event Processing**: Guarantees exactly-once reward application
- **Cache Invalidation**: Real-time configuration updates via PostgreSQL LISTEN/NOTIFY
- **Quality Modifiers**: Content-aware XP calculations for messages
- **Audit Trail**: Complete mutation history with before/after state snapshots
- **OAuth Security**: Discord-verified admin access with JWT session management
- **Performance**: Optimized queries with partial indexes and connection pooling

### Architecture
- **4-Service Stack**: PostgreSQL 16, Discord bot (discord.py), FastAPI REST API, SvelteKit dashboard
- **Event Pipeline**: Discord Event → SynapseEvent → Zone Classification → Quality Modifier → Anti-Gaming → Multiplier Application → XP Cap → Idempotent Persist → Stat Update → Achievement Check → Level-Up Check
- **Async-Ready**: SQLAlchemy engine with asyncio.to_thread for Discord bot integration

### Documentation
- Comprehensive README with architecture diagrams, setup instructions, and API overview
- Design documents covering vision, architecture, dual economy, database schema, reward engine, achievements, admin panel, and deployment
- Implementation decisions and requirements trace documents
- Seed data templates for achievements, settings, and zones

### Deferred to Future Releases
- GitHub Neural Bridge (webhook integration for code contribution XP)
- LLM-based content quality modifiers (stub present, ready for integration)
- Quest system (database tables exist, UI deferred)
- Alembic database migrations (using `create_all` for initial release)
- Custom achievement badge images (column exists, rendering deferred)
- DM notification delivery (preference storage implemented, delivery deferred)

---

**Full Changelog**: https://github.com/yourusername/synapse/commits/v1.0.0
