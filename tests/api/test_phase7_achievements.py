"""
tests.test_phase7_achievements — Phase 7: Achievement System v2 Tests
======================================================================

Tests the achievement taxonomy seeder (rarities, categories, seasons)
and the new ``dispatch_achievement`` outcome type in the RuleEngine.

No real database, no Docker, no Discord required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from synapse.engine.events import InteractionType, SynapseEvent
from synapse.engine.rule_engine import RuleEngine, RuleEvaluationResult
from synapse.services.achievement_seeder import (
    _DEFAULT_CATEGORIES,
    _DEFAULT_RARITIES,
    seed_default_season,
    seed_default_taxonomy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_ctx(session_obj):
    """Wrap a MagicMock session so ``with Session(engine) as s:`` works."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session_obj)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_event(
    event_type: InteractionType = InteractionType.MESSAGE,
    context: dict | None = None,
) -> SynapseEvent:
    return SynapseEvent(
        user_id=42,
        guild_id=1000,
        channel_id=9000,
        event_type=event_type,
        source_event_id="msg_999",
        metadata={},
        context=context or {},
    )


def _make_rule(
    name: str = "rule",
    outcomes: list | None = None,
    predicates: list | None = None,
    priority: int = 50,
) -> dict:
    return {
        "id": 1,
        "name": name,
        "priority": priority,
        "predicates": predicates or [],
        "outcomes": outcomes or [],
    }


# ---------------------------------------------------------------------------
# TestSeedDefaultTaxonomy
# ---------------------------------------------------------------------------


class TestSeedDefaultTaxonomy:
    def _build_session(self, existing_rarities: list[str], existing_cats: list[str]):
        session = MagicMock()

        _call_count = {"n": 0}

        def scalars_side_effect(stmt):
            # First call loads rarities, second call loads categories
            idx = _call_count["n"]
            _call_count["n"] += 1
            inner = MagicMock()
            if idx == 0:
                inner.all.return_value = existing_rarities
            else:
                inner.all.return_value = existing_cats
            return inner

        session.scalars.side_effect = scalars_side_effect
        return session

    def test_seeds_all_on_empty_db(self):
        engine = MagicMock()
        session = self._build_session([], [])

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = seed_default_taxonomy(engine, guild_id=9999)

        assert result["rarities"] == len(_DEFAULT_RARITIES)
        assert result["categories"] == len(_DEFAULT_CATEGORIES)
        assert session.add.call_count == len(_DEFAULT_RARITIES) + len(_DEFAULT_CATEGORIES)
        session.commit.assert_called_once()

    def test_idempotent_all_exist(self):
        engine = MagicMock()
        existing_r = [d["name"] for d in _DEFAULT_RARITIES]
        existing_c = [d["name"] for d in _DEFAULT_CATEGORIES]
        session = self._build_session(existing_r, existing_c)

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = seed_default_taxonomy(engine, guild_id=9999)

        assert result["rarities"] == 0
        assert result["categories"] == 0
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_partial_seed_missing_rarities(self):
        """If all categories exist but no rarities, only rarities are inserted."""
        engine = MagicMock()
        existing_c = [d["name"] for d in _DEFAULT_CATEGORIES]
        session = self._build_session([], existing_c)

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = seed_default_taxonomy(engine, guild_id=9999)

        assert result["rarities"] == len(_DEFAULT_RARITIES)
        assert result["categories"] == 0
        assert session.add.call_count == len(_DEFAULT_RARITIES)

    def test_partial_seed_missing_categories(self):
        """If all rarities exist but no categories, only categories are inserted."""
        engine = MagicMock()
        existing_r = [d["name"] for d in _DEFAULT_RARITIES]
        session = self._build_session(existing_r, [])

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = seed_default_taxonomy(engine, guild_id=9999)

        assert result["rarities"] == 0
        assert result["categories"] == len(_DEFAULT_CATEGORIES)

    def test_default_rarities_have_expected_names(self):
        names = {d["name"] for d in _DEFAULT_RARITIES}
        assert {"Common", "Uncommon", "Rare", "Epic", "Legendary"} == names

    def test_default_categories_have_expected_names(self):
        names = {d["name"] for d in _DEFAULT_CATEGORIES}
        assert {"General", "Social", "Activity", "Milestone", "Special"} == names

    def test_rarity_sort_orders_are_distinct(self):
        orders = [d["sort_order"] for d in _DEFAULT_RARITIES]
        assert len(set(orders)) == len(orders), "sort_order values should be unique"

    def test_category_sort_orders_are_distinct(self):
        orders = [d["sort_order"] for d in _DEFAULT_CATEGORIES]
        assert len(set(orders)) == len(orders), "sort_order values should be unique"

    def test_race_condition_returns_zeros(self):
        """IntegrityError during commit is silently handled, returns 0/0."""
        from sqlalchemy.exc import IntegrityError

        engine = MagicMock()
        session = self._build_session([], [])
        session.commit.side_effect = IntegrityError("dup", None, None)

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            result = seed_default_taxonomy(engine, guild_id=9999)

        assert result == {"rarities": 0, "categories": 0}


# ---------------------------------------------------------------------------
# TestSeedDefaultSeason
# ---------------------------------------------------------------------------


class TestSeedDefaultSeason:
    def test_creates_season_when_none_exists(self):
        engine = MagicMock()
        session = MagicMock()
        session.scalar.return_value = None  # no existing season

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            created = seed_default_season(engine, guild_id=7777)

        assert created is True
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.guild_id == 7777
        assert added.name == "Founding Season"
        assert added.active is True
        session.commit.assert_called_once()

    def test_no_op_when_season_exists(self):
        engine = MagicMock()
        session = MagicMock()
        session.scalar.return_value = 42  # existing season id

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            created = seed_default_season(engine, guild_id=7777)

        assert created is False
        session.add.assert_not_called()
        session.commit.assert_not_called()

    def test_season_dates_are_chronological(self):
        engine = MagicMock()
        session = MagicMock()
        session.scalar.return_value = None

        added_seasons = []

        def capture_add(obj):
            added_seasons.append(obj)

        session.add.side_effect = capture_add

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            seed_default_season(engine, guild_id=7777)

        assert len(added_seasons) == 1
        s = added_seasons[0]
        assert s.ends_at > s.starts_at

    def test_race_condition_returns_false(self):
        from sqlalchemy.exc import IntegrityError

        engine = MagicMock()
        session = MagicMock()
        session.scalar.return_value = None
        session.commit.side_effect = IntegrityError("dup", None, None)

        with patch(
            "synapse.services.achievement_seeder.Session",
            return_value=_mock_session_ctx(session),
        ):
            created = seed_default_season(engine, guild_id=7777)

        assert created is False


# ---------------------------------------------------------------------------
# TestDispatchAchievementOutcome — RuleEngine pure tests
# ---------------------------------------------------------------------------


class TestDispatchAchievementOutcome:
    def test_achievement_outcome_collected_in_results(self):
        """A rule with achievement outcome yields template_name in outcomes_applied."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(outcomes=[{"type": "achievement", "template_name": "First Steps"}])

        result = engine.evaluate(event, [rule], {})

        assert result.outcomes_applied["achievements"] == ["First Steps"]

    def test_achievement_outcome_by_template_id(self):
        """template_id (int) is also accepted as an achievement reference."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(outcomes=[{"type": "achievement", "template_id": 7}])

        result = engine.evaluate(event, [rule], {})

        assert result.outcomes_applied["achievements"] == [7]

    def test_numeric_and_achievement_outcomes_coexist(self):
        """XP and achievement outcomes from the same rule are both collected."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(
            outcomes=[
                {"type": "xp", "base_value": 20},
                {"type": "achievement", "template_name": "Chatterbox"},
            ]
        )

        result = engine.evaluate(event, [rule], {})

        assert result.outcomes_applied["xp"] == 20
        assert result.outcomes_applied["achievements"] == ["Chatterbox"]

    def test_multiple_achievement_outcomes_accumulate(self):
        """Two achievement outcomes in one rule both appear in the list."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(
            outcomes=[
                {"type": "achievement", "template_name": "Alpha"},
                {"type": "achievement", "template_name": "Beta"},
            ]
        )

        result = engine.evaluate(event, [rule], {})

        assert set(result.outcomes_applied["achievements"]) == {"Alpha", "Beta"}

    def test_achievements_across_multiple_rules(self):
        """Achievement outcomes from multiple matched rules are all collected."""
        engine = RuleEngine()
        event = _make_event()
        rule_a = {
            "id": 1,
            "name": "rule_a",
            "priority": 100,
            "predicates": [],
            "outcomes": [{"type": "achievement", "template_name": "Pioneer"}],
        }
        rule_b = {
            "id": 2,
            "name": "rule_b",
            "priority": 50,
            "predicates": [],
            "outcomes": [{"type": "achievement", "template_name": "Explorer"}],
        }

        result = engine.evaluate(event, [rule_a, rule_b], {})

        assert set(result.outcomes_applied["achievements"]) == {"Pioneer", "Explorer"}

    def test_achievement_outcome_missing_ref_is_skipped(self):
        """Outcome with type=achievement but no template name/id is silently dropped."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(outcomes=[{"type": "achievement"}])

        result = engine.evaluate(event, [rule], {})

        assert result.outcomes_applied["achievements"] == []

    def test_no_achievement_outcomes_gives_empty_list(self):
        """Evaluations with only numeric outcomes always have empty achievements list."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(outcomes=[{"type": "xp", "base_value": 10}])

        result = engine.evaluate(event, [rule], {})

        assert "achievements" in result.outcomes_applied
        assert result.outcomes_applied["achievements"] == []

    def test_no_matching_rules_gives_empty_achievements(self):
        """When no rules match, outcomes_applied is empty dict (no achievements key)."""
        engine = RuleEngine()
        event = _make_event()

        result = engine.evaluate(event, [], {})

        assert result.outcomes_applied.get("achievements", []) == []

    def test_achievement_case_insensitive_outcome_type(self):
        """Outcome type matching is case-insensitive: 'ACHIEVEMENT' is valid."""
        engine = RuleEngine()
        event = _make_event()
        rule = _make_rule(outcomes=[{"type": "ACHIEVEMENT", "template_name": "Champion"}])

        result = engine.evaluate(event, [rule], {})

        assert result.outcomes_applied["achievements"] == ["Champion"]


# ---------------------------------------------------------------------------
# TestAchievementsToDispatch — RuleEvaluationResult property
# ---------------------------------------------------------------------------


class TestAchievementsToDispatch:
    def test_property_returns_list_when_achievements_present(self):
        result = RuleEvaluationResult(outcomes_applied={"xp": 10, "achievements": ["First Steps"]})
        assert result.achievements_to_dispatch == ["First Steps"]

    def test_property_returns_empty_list_when_no_achievements(self):
        result = RuleEvaluationResult(
            outcomes_applied={"xp": 10, "gold": 0, "achievements": []}
        )
        assert result.achievements_to_dispatch == []

    def test_property_returns_empty_list_when_key_missing(self):
        result = RuleEvaluationResult(outcomes_applied={"xp": 5})
        assert result.achievements_to_dispatch == []

    def test_property_works_on_empty_outcomes(self):
        result = RuleEvaluationResult()
        assert result.achievements_to_dispatch == []
