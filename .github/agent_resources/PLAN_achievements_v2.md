# PLAN: Achievement System v2

## Problem Statement

The current achievement system is a minimal scaffold with no enforcement, limited trigger
types, and a UX that assumes the admin already knows the schema. It needs to become a
first-class system on par with Reward Rules — admin-friendly, extensible, and powerful.

### Pain points (user-reported)

1. **No enforcement** — requirement_type, requirement_field, category, rarity are all raw
   text inputs. A new admin has zero guidance.
2. **Rigid categories & rarities** — hardcoded in `dashboard/src/lib/constants.ts` as
   `['social', 'coding', 'engagement', 'special']` and
   `['common', 'uncommon', 'rare', 'epic', 'legendary']`. No way to customize.
3. **Limited trigger types** — only `counter_threshold`, `star_threshold`, `xp_milestone`
   actually fire. No event-driven triggers.
4. **No event-driven achievements** — can't trigger on member join, invite count, reaching
   a specific level, etc.
5. **No series / progression** — can't create "Novice → Apprentice → Veteran → Master"
   chains where each tier unlocks at a higher threshold.
6. **No incremental milestones** — can't say "every 10 levels, award a badge."
7. **Badge images are URL-only** — no upload/storage support.
8. **Single requirement_value** — can't express compound conditions or ranges.

---

## Current Architecture (what we're replacing)

```
AchievementTemplate (flat table)
  ├─ requirement_type: String(50)   ← free text, no enum
  ├─ requirement_field: String(50)  ← free text
  ├─ requirement_value: Integer     ← single threshold
  ├─ category: String(50)           ← free text
  └─ rarity: String(20)            ← free text

check_achievements() — 3 hardcoded if/elif branches
  ├─ counter_threshold  → stats[field] >= value
  ├─ star_threshold     → stars >= value
  └─ xp_milestone       → xp >= value
```

---

## Proposed Design

### Core Concepts

#### 1. Trigger Types (replaces `requirement_type`)

A **trigger type** defines *what event causes the check*. Each has a well-defined schema
for its configuration.

| Trigger Type | Description | Config Schema | When Checked |
|---|---|---|---|
| `stat_threshold` | A UserStats counter reaches N | `{ field: "messages_sent", value: 100 }` | After any event that increments the stat |
| `xp_milestone` | Total XP reaches N | `{ value: 5000 }` | After XP update |
| `star_milestone` | Stars reach N | `{ scope: "season"\|"lifetime", value: 500 }` | After star update |
| `level_reached` | User hits level N | `{ value: 10 }` | On level-up |
| `level_interval` | Every N levels (10, 20, 30...) | `{ interval: 10 }` | On level-up |
| `event_count` | N occurrences of a specific event type | `{ event_type: "VOICE_JOIN", count: 50 }` | After matching event |
| `first_event` | First time a specific event occurs | `{ event_type: "MESSAGE" }` | After matching event |
| `member_tenure` | N days since join | `{ days: 365 }` | Daily cron or on activity |
| `invite_count` | N successful invites | `{ count: 10 }` | On member join (invite tracking) |
| `manual` | Admin-granted only | `{}` | Never auto-triggered |

> **Note:** `invite_count` and `member_tenure` require new data sources that may not exist
> yet. These can be Phase 3 additions — the schema should support them from day one even
> if the trigger logic isn't wired.

#### 2. Achievement Series (progression chains)

A **series** is a group of achievements that form a progression path. Each achievement in
a series has a `series_id` and an `order` (rank in the chain).

```
Series: "Social Butterfly"
  ├─ Tier 1: "Chatterbox"      — 100 messages   (Common)
  ├─ Tier 2: "Conversationalist" — 500 messages  (Uncommon)
  ├─ Tier 3: "Community Pillar"  — 2000 messages (Rare)
  └─ Tier 4: "Social Legend"     — 10000 messages (Legendary)
```

**Rules:**
- Tiers unlock sequentially (can't get Tier 3 without Tier 2)
- Each tier is its own `AchievementTemplate` row with its own rewards
- The series is a thin grouping table (`AchievementSeries`)
- Dashboard shows series as collapsible groups

#### 3. Admin-Customizable Categories & Rarities

Instead of hardcoded arrays, store them as guild-level settings:

**Option A: Settings table** — Store as JSON arrays in the `settings` table
(`achievement_categories`, `achievement_rarities`). Simple, no migration for adding values.

**Option B: Dedicated tables** — `AchievementCategory(id, guild_id, name, icon, sort_order)`
and `AchievementRarity(id, guild_id, name, color, sort_order)`. More structured, supports
metadata per entry.

**Recommendation: Option A** for categories (they're just labels), **Option B** for
rarities (because rarities have associated colors/weights for display and could drive
drop rates or other mechanics later).

Actually, let's reconsider. Both categories and rarities benefit from per-guild
customization with metadata (icons, colors, sort order). Let's use **Option B for both**
but keep sensible defaults seeded on guild setup.

#### 4. Achievement Trigger Config (replaces requirement_field + requirement_value)

Replace the three separate columns with a single JSONB column:

```python
trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
trigger_config: Mapped[dict] = mapped_column(JSONB, default=dict)
```

Each `trigger_type` has a known JSON schema. The engine validates configs, and the
dashboard renders dynamic forms based on the selected trigger type.

#### 5. Badge Image Storage

**Option A: Local upload via API** — Store images in a configurable directory
(e.g., `data/badges/`), serve via a static file route. Simple.

**Option B: S3/object storage** — More production-ready, but adds infrastructure.

**Option C: Both** — Support URL and upload, store uploaded files locally with an optional
S3 backend later.

**Recommendation: Option C** — Accept uploads via a `POST /admin/badges/upload` endpoint,
store locally in `data/badges/{guild_id}/`, serve via `GET /badges/{filename}`. Keep the
URL field as a fallback. The model stores either a URL or a local path reference.

---

## Schema Changes

### New/Modified Tables

```python
# --- New: AchievementCategory ---
class AchievementCategory(Base):
    __tablename__ = "achievement_categories"
    id: Mapped[int]           # PK
    guild_id: Mapped[int]     # FK → guild context
    name: Mapped[str]         # e.g., "Social", "Voice", "Special"
    icon: Mapped[str | None]  # emoji or icon class
    sort_order: Mapped[int]   # display order
    # Unique(guild_id, name)

# --- New: AchievementRarity ---
class AchievementRarity(Base):
    __tablename__ = "achievement_rarities"
    id: Mapped[int]           # PK
    guild_id: Mapped[int]
    name: Mapped[str]         # e.g., "Common", "Legendary"
    color: Mapped[str]        # hex color for badge/border
    weight: Mapped[int]       # sort order / relative rank
    # Unique(guild_id, name)

# --- New: AchievementSeries ---
class AchievementSeries(Base):
    __tablename__ = "achievement_series"
    id: Mapped[int]           # PK
    guild_id: Mapped[int]
    name: Mapped[str]         # "Social Butterfly"
    description: Mapped[str | None]
    # Unique(guild_id, name)

# --- Modified: AchievementTemplate ---
class AchievementTemplate(Base):
    # KEEP: id, guild_id, name, description, xp_reward, gold_reward, active, created_at,
    #       announce_channel_id, earned_by relationship
    # REPLACE:
    #   requirement_type     → trigger_type (String(30), constrained by TriggerType StrEnum)
    #   requirement_field    → (dropped, merged into trigger_config)
    #   requirement_value    → (dropped, merged into trigger_config)
    #   requirement_scope    → (dropped, merged into trigger_config)
    #   category (String)    → category_id (FK → achievement_categories.id, nullable)
    #   rarity (String)      → rarity_id (FK → achievement_rarities.id, nullable)
    #   badge_image_url      → badge_image (String(500)) — URL or local path
    # ADD:
    #   trigger_config: JSONB — configuration for the trigger type
    #   series_id: FK → achievement_series.id (nullable)
    #   series_order: Integer (nullable) — position in series
    #   is_hidden: Boolean — hide until earned (secret achievements)
    #   max_earners: Integer | None — limit how many users can earn it
```

### New Enum

```python
class TriggerType(enum.StrEnum):
    STAT_THRESHOLD = "stat_threshold"
    XP_MILESTONE = "xp_milestone"
    STAR_MILESTONE = "star_milestone"
    LEVEL_REACHED = "level_reached"
    LEVEL_INTERVAL = "level_interval"
    EVENT_COUNT = "event_count"
    FIRST_EVENT = "first_event"
    MEMBER_TENURE = "member_tenure"   # Phase 3
    INVITE_COUNT = "invite_count"     # Phase 3
    MANUAL = "manual"
```

---

## Engine Redesign

The current `check_achievements()` is a flat if/elif chain. The new design uses a
**trigger handler registry**:

```python
# Mapping of trigger types to handler functions
TRIGGER_HANDLERS: dict[TriggerType, Callable] = {
    TriggerType.STAT_THRESHOLD: _check_stat_threshold,
    TriggerType.XP_MILESTONE: _check_xp_milestone,
    TriggerType.STAR_MILESTONE: _check_star_milestone,
    TriggerType.LEVEL_REACHED: _check_level_reached,
    TriggerType.LEVEL_INTERVAL: _check_level_interval,
    TriggerType.EVENT_COUNT: _check_event_count,
    TriggerType.FIRST_EVENT: _check_first_event,
    # MANUAL has no handler — never auto-triggered
}
```

Each handler receives a standardized context:

```python
@dataclass(frozen=True, slots=True)
class AchievementContext:
    user_xp: int
    user_level: int
    old_level: int | None  # for level-up triggers
    season_stars: int
    lifetime_stars: int
    stats: dict[str, int]
    event_type: InteractionType | None
    event_count_map: dict[str, int] | None  # event_type → total count
```

The main `check_achievements()` function becomes:

```python
def check_achievements(
    guild_id: int,
    cache: ConfigCache,
    ctx: AchievementContext,
    already_earned: set[int],
) -> list[int]:
    templates = cache.get_active_achievements(guild_id)
    newly_earned = []
    for t in templates:
        if t.id in already_earned:
            continue
        # Series gating: if in a series, previous tier must be earned
        if t.series_id and t.series_order and t.series_order > 1:
            prev = cache.get_series_predecessor(t.series_id, t.series_order)
            if prev and prev.id not in already_earned:
                continue
        handler = TRIGGER_HANDLERS.get(TriggerType(t.trigger_type))
        if handler and handler(t.trigger_config, ctx):
            newly_earned.append(t.id)
    return newly_earned
```

---

## Dashboard UX Improvements

### Trigger Type Selector
- **Dropdown** (not free text) with human-readable labels + descriptions
- Selecting a type reveals a **dynamic config form** for that trigger
  - `stat_threshold` → dropdown of stat fields + number input
  - `level_reached` → single number input ("Reach level ___")
  - `level_interval` → number input ("Every ___ levels")
  - `event_count` → dropdown of event types + count input
  - `manual` → no config needed (just a note: "Admin-granted only")

### Series Management
- New tab/section: "Achievement Series"
- Create a series → add tiers with drag-and-drop ordering
- Each tier auto-gets the series category/rarity progression

### Category & Rarity Management
- New section in Settings (or inline on Achievements page)
- Add/edit/reorder categories with icons
- Add/edit/reorder rarities with colors
- Seed defaults on first load (social, engagement, voice, special / common→legendary)

### Badge Upload
- File input alongside URL field
- Preview thumbnail
- Drag-and-drop support
- Store in `data/badges/{guild_id}/` and serve via API

---

## Rollout Phases

### Phase 1: Schema & Engine Foundation
- Add `TriggerType` enum to models
- Add new tables: `AchievementCategory`, `AchievementRarity`, `AchievementSeries`
- Migrate `AchievementTemplate`: add `trigger_type`, `trigger_config`, `series_id`,
  `series_order`, `is_hidden`, `max_earners`; FK to category/rarity tables
- Data migration: convert existing `requirement_type` → `trigger_type` + `trigger_config`
- Rewrite `check_achievements()` with handler registry
- Update `ConfigCache` (index by trigger type, series predecessor lookup)
- Update `admin_service` and `reward_service`
- Add to `ALLOWED_NOTIFY_TABLES`
- Tests passing
- **Success criteria:** Existing achievements still work, new trigger types compile

### Phase 2: API & Dashboard — Core UX
- Update admin API routes (CRUD for categories, rarities, series)
- Update achievement CRUD routes for new schema
- Dashboard: trigger type dropdown with dynamic config forms
- Dashboard: category & rarity management (inline or in settings)
- Dashboard: series creation and tier management
- Badge upload endpoint + dashboard file input
- Tests passing
- **Success criteria:** Admin can create achievements with all new trigger types via UI

### Phase 3: Advanced Triggers & Polish
- Wire `level_reached` and `level_interval` triggers in the level-up code path
- Wire `event_count` and `first_event` via Event Lake queries or activity_log counts
- `member_tenure` trigger (requires join date tracking — may already exist on User)
- `invite_count` trigger (requires invite tracking infrastructure)
- Secret/hidden achievements in public-facing pages
- `max_earners` enforcement
- Series display on public achievements page
- Tests for all new trigger types
- **Success criteria:** All trigger types fire correctly in production

---

## Decisions (resolved)

1. **Category & rarity storage:** → **Dedicated tables.** Both `AchievementCategory` and
   `AchievementRarity` get their own tables with per-guild customization, icons/colors,
   and sort order.

2. **Level interval semantics:** → **Each tier is its own template.** No repeatable earns.
   Progression = a series of distinct templates, each with its own name, icon/image, and
   rewards. A "Level Interval" trigger just means the admin defines each tier explicitly
   as part of a series. The `level_interval` trigger type checks "user level is a multiple
   of N" but each matching level should correspond to a pre-created tier template.

3. **Event count source:** → **Activity log queries.** Stability over speed. Even if it
   takes seconds, that's fine for a non-real-time check.

4. **Badge storage location:** → `data/badges/{guild_id}/` default, configurable via
   `config.yaml` later if needed.

5. **Migration strategy:** → **Hard cut.** No compatibility period. We are pre-users with
   zero live data. Nuke and rebuild freely.

6. **Backward compatibility:** → **None needed.** Full freedom to restructure.
