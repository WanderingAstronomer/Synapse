"""
tests.test_rule_engine — Unit Tests for the Rule Engine
========================================================

Entirely deterministic — no database, no Discord, no fixtures required.
Tests the pure ``RuleEngine.evaluate`` pipeline and the helper functions
it delegates to (``evaluate_predicate``, ``resolve_scaling``).
"""

from __future__ import annotations

import pytest

from synapse.engine.events import InteractionType, SynapseEvent
from synapse.engine.reward import evaluate_predicate, resolve_scaling
from synapse.engine.rule_engine import RuleEngine, RuleEvaluationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_type: InteractionType = InteractionType.MESSAGE,
    metadata: dict | None = None,
    context: dict | None = None,
    source_event_id: str | None = "msg_123",
) -> SynapseEvent:
    return SynapseEvent(
        user_id=42,
        guild_id=1000,
        channel_id=9000,
        event_type=event_type,
        source_event_id=source_event_id,
        metadata=metadata or {},
        context=context or {},
    )


def _make_rule(
    name: str = "test_rule",
    predicates: list | None = None,
    outcomes: list | None = None,
    priority: int = 100,
) -> dict:
    return {
        "id": 1,
        "name": name,
        "priority": priority,
        "predicates": predicates or [],
        "outcomes": outcomes or [{"type": "xp", "base_value": 0}],
    }


# ---------------------------------------------------------------------------
# evaluate_predicate
# ---------------------------------------------------------------------------


class TestEvaluatePredicate:
    def test_eq_matching(self):
        event = _make_event(event_type=InteractionType.MESSAGE)
        pred = {"field": "event_type", "op": "==", "value": "MESSAGE"}
        assert evaluate_predicate(event, pred) is True

    def test_eq_non_matching(self):
        event = _make_event(event_type=InteractionType.REACTION_GIVEN)
        pred = {"field": "event_type", "op": "==", "value": "MESSAGE"}
        assert evaluate_predicate(event, pred) is False

    def test_neq(self):
        event = _make_event(event_type=InteractionType.VOICE_TICK)
        pred = {"field": "event_type", "op": "!=", "value": "MESSAGE"}
        assert evaluate_predicate(event, pred) is True

    def test_gte_above(self):
        event = _make_event(context={"user_level": 5})
        pred = {"field": "context.user_level", "op": ">=", "value": 3}
        assert evaluate_predicate(event, pred) is True

    def test_gte_equal(self):
        event = _make_event(context={"user_level": 5})
        pred = {"field": "context.user_level", "op": ">=", "value": 5}
        assert evaluate_predicate(event, pred) is True

    def test_gte_below(self):
        event = _make_event(context={"user_level": 2})
        pred = {"field": "context.user_level", "op": ">=", "value": 5}
        assert evaluate_predicate(event, pred) is False

    def test_lte(self):
        event = _make_event(context={"messages_today": 10})
        pred = {"field": "context.messages_today", "op": "<=", "value": 100}
        assert evaluate_predicate(event, pred) is True

    def test_gt_false(self):
        event = _make_event(context={"user_xp": 50})
        pred = {"field": "context.user_xp", "op": ">", "value": 100}
        assert evaluate_predicate(event, pred) is False

    def test_lt_true(self):
        event = _make_event(context={"voice_minutes_today": 5})
        pred = {"field": "context.voice_minutes_today", "op": "<", "value": 60}
        assert evaluate_predicate(event, pred) is True

    def test_contains_in_metadata(self):
        event = _make_event(metadata={"tags": ["art", "media"]})
        pred = {"field": "metadata.tags", "op": "contains", "value": "art"}
        assert evaluate_predicate(event, pred) is True

    def test_contains_not_found(self):
        event = _make_event(metadata={"tags": ["art"]})
        pred = {"field": "metadata.tags", "op": "contains", "value": "music"}
        assert evaluate_predicate(event, pred) is False

    def test_unknown_op_defaults_false(self):
        event = _make_event()
        pred = {"field": "event_type", "op": "unknown_op", "value": "MESSAGE"}
        assert evaluate_predicate(event, pred) is False

    def test_missing_context_field_is_falsy(self):
        event = _make_event(context={})
        pred = {"field": "context.missing_key", "op": ">=", "value": 1}
        assert evaluate_predicate(event, pred) is False


# ---------------------------------------------------------------------------
# resolve_scaling
# ---------------------------------------------------------------------------


class TestResolveScaling:
    def test_linear_scaling(self):
        # formula: base * n * factor  (n = context variable value)
        context = {"user_level": 4}
        scaling = {"curve": "linear", "variable": "user_level", "factor": 2.0}
        result = resolve_scaling(10, scaling, context)
        assert result == pytest.approx(10 * 4 * 2.0)  # 80.0

    def test_logarithmic_scaling(self):
        # formula: base * log_b(n) * factor
        import math

        context = {"messages_today": 100}
        scaling = {"curve": "logarithmic", "variable": "messages_today", "factor": 1.0, "base": 10}
        result = resolve_scaling(10, scaling, context)
        assert result == pytest.approx(10 * math.log(100, 10) * 1.0)  # 20.0

    def test_scaling_missing_variable_returns_base(self):
        context = {}
        scaling = {"curve": "linear", "variable": "nonexistent", "factor": 5.0}
        result = resolve_scaling(10, scaling, context)
        # n defaults to 1 when variable missing: 10 * 1 * 5.0 = 50
        assert result == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# RuleEngine.evaluate — basic cases
# ---------------------------------------------------------------------------


class TestRuleEngineEvaluate:
    def test_no_rules_returns_empty_result(self):
        event = _make_event()
        result = RuleEngine().evaluate(event, [], {})
        assert isinstance(result, RuleEvaluationResult)
        assert result.matched_rules == []
        assert result.outcomes_applied == {}

    def test_matching_rule_recorded(self):
        event = _make_event(event_type=InteractionType.MESSAGE)
        rule = _make_rule(
            name="message_reward",
            predicates=[{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            outcomes=[{"type": "xp", "base_value": 10}],
        )
        result = RuleEngine().evaluate(event, [rule], {})
        assert len(result.matched_rules) == 1
        assert result.matched_rules[0]["rule_name"] == "message_reward"

    def test_non_matching_rule_not_recorded(self):
        event = _make_event(event_type=InteractionType.REACTION_GIVEN)
        rule = _make_rule(
            predicates=[{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            outcomes=[{"type": "xp", "base_value": 10}],
        )
        result = RuleEngine().evaluate(event, [rule], {})
        assert result.matched_rules == []

    def test_xp_accumulated_correctly(self):
        event = _make_event(event_type=InteractionType.MESSAGE)
        rule = _make_rule(
            predicates=[{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            outcomes=[{"type": "xp", "base_value": 25}],
        )
        result = RuleEngine().evaluate(event, [rule], {})
        assert result.outcomes_applied.get("xp", 0) == 25

    def test_multiple_outcomes_on_one_rule(self):
        event = _make_event(event_type=InteractionType.REACTION_RECEIVED)
        rule = _make_rule(
            predicates=[{"field": "event_type", "op": "==", "value": "REACTION_RECEIVED"}],
            outcomes=[
                {"type": "xp", "base_value": 5},
                {"type": "gold", "base_value": 2},
            ],
        )
        result = RuleEngine().evaluate(event, [rule], {})
        assert result.outcomes_applied.get("xp") == 5
        assert result.outcomes_applied.get("gold") == 2

    def test_multiple_rules_accumulate(self):
        event = _make_event(event_type=InteractionType.MESSAGE)
        rule_a = _make_rule(
            name="base_xp",
            predicates=[{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            outcomes=[{"type": "xp", "base_value": 10}],
            priority=100,
        )
        rule_b = {
            "id": 2,
            "name": "bonus_xp",
            "priority": 50,
            "predicates": [{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            "outcomes": [{"type": "xp", "base_value": 5}],
        }
        result = RuleEngine().evaluate(event, [rule_a, rule_b], {})
        assert result.outcomes_applied.get("xp") == 15
        assert len(result.matched_rules) == 2

    def test_rules_sorted_by_priority_descending(self):
        event = _make_event(event_type=InteractionType.MESSAGE)
        rule_low = {
            "id": 1,
            "name": "low",
            "priority": 10,
            "predicates": [{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            "outcomes": [{"type": "xp", "base_value": 1}],
        }
        rule_high = {
            "id": 2,
            "name": "high",
            "priority": 200,
            "predicates": [{"field": "event_type", "op": "==", "value": "MESSAGE"}],
            "outcomes": [{"type": "xp", "base_value": 1}],
        }
        result = RuleEngine().evaluate(event, [rule_low, rule_high], {})
        names = [r["rule_name"] for r in result.matched_rules]
        assert names == ["high", "low"]


# ---------------------------------------------------------------------------
# Context snapshot
# ---------------------------------------------------------------------------


class TestContextSnapshot:
    def test_context_captured_in_result(self):
        ctx = {"user_level": 7, "messages_today": 42}
        event = _make_event(context=ctx)
        result = RuleEngine().evaluate(event, [], ctx)
        assert result.context_snapshot == ctx

    def test_context_is_copy_not_reference(self):
        ctx: dict = {"user_level": 3}
        event = _make_event(context=ctx)
        result = RuleEngine().evaluate(event, [], ctx)
        ctx["user_level"] = 99  # mutate after evaluate
        assert result.context_snapshot["user_level"] == 3


# ---------------------------------------------------------------------------
# Scaled outcomes
# ---------------------------------------------------------------------------


class TestScaledOutcomes:
    def test_scaled_xp_greater_than_base(self):
        # linear(base=10, n=5, factor=1.0) = 10 * 5 * 1.0 = 50 > 10
        ctx = {"user_level": 5}
        event = _make_event(context=ctx)
        rule = _make_rule(
            predicates=[],
            outcomes=[
                {
                    "type": "xp",
                    "base_value": 10,
                    "scaling": {
                        "curve": "linear",
                        "variable": "user_level",
                        "factor": 1.0,
                    },
                }
            ],
        )
        result = RuleEngine().evaluate(event, [rule], ctx)
        assert result.outcomes_applied.get("xp", 0) > 10
        assert result.outcomes_applied.get("xp", 0) == 50

    def test_empty_predicates_always_matches(self):
        event = _make_event(event_type=InteractionType.VOICE_TICK)
        rule = _make_rule(
            predicates=[],
            outcomes=[{"type": "xp", "base_value": 7}],
        )
        result = RuleEngine().evaluate(event, [rule], {})
        assert len(result.matched_rules) == 1
        assert result.outcomes_applied.get("xp") == 7

    def test_multiple_predicates_all_must_match(self):
        """All predicates in a rule are ANDed — a single false predicate skips the rule."""
        event = _make_event(
            event_type=InteractionType.MESSAGE,
            context={"user_level": 2},
        )
        rule = _make_rule(
            predicates=[
                {"field": "event_type", "op": "==", "value": "MESSAGE"},
                {"field": "context.user_level", "op": ">=", "value": 10},  # fails
            ],
            outcomes=[{"type": "xp", "base_value": 50}],
        )
        result = RuleEngine().evaluate(event, [rule], event.context)
        assert result.matched_rules == []
        assert result.outcomes_applied.get("xp", 0) == 0
