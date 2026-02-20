"""
synapse.engine.rule_engine — Pure Rule Evaluation Engine
=========================================================

Evaluates a list of ``RewardRule`` dicts against a ``SynapseEvent`` and
returns a deterministic ``RuleEvaluationResult``.

Architecture
------------
This module is **pure**: no database I/O, no Discord I/O.  All inputs are
plain Python values; all outputs are immutable dataclasses.  The service
layer (``reward_service``) is responsible for loading rules from the DB,
injecting context, and persisting evaluation traces.

Predicate & scaling evaluation delegates to the existing helpers in
``synapse.engine.reward`` (``evaluate_predicate``, ``resolve_scaling``),
which are already proven and tested.

Rule dict format (matches ``RewardRule.predicates`` / ``.outcomes`` JSONB)
--------------------------------------------------------------------------
::

    {
        "id": 1,
        "name": "default:MESSAGE",
        "priority": 50,
        "predicates": [
            {"field": "event_type", "op": "==", "value": "MESSAGE"}
        ],
        "outcomes": [
            {"type": "XP",    "base_value": 15},
            {"type": "XP",    "base_value": 5,
             "scaling": {"curve": "LOGARITHMIC", "variable": "messages_today",
                         "factor": 0.5, "base": 10}}
        ]
    }

Context dict keys (populated by the service layer from ``event_counters``)
---------------------------------------------------------------------------
- ``messages_today``     — messages sent in the current UTC day
- ``reactions_today``    — reactions given in the current UTC day
- ``voice_minutes_today`` — voice active minutes in the current UTC day
- ``messages_lifetime``  — total messages sent (lifetime period)
- ``user_level``         — resolved from ``User.level``
- ``user_xp``            — resolved from ``User.xp``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from synapse.engine.reward import evaluate_predicate, resolve_scaling

if TYPE_CHECKING:
    from synapse.engine.events import SynapseEvent

logger = logging.getLogger(__name__)

__all__ = ["RuleEngine", "RuleEvaluationResult"]


# ---------------------------------------------------------------------------
# RuleEvaluationResult — output of the engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuleEvaluationResult:
    """Immutable output of a single rule engine evaluation pass.

    Parameters
    ----------
    matched_rules : list[dict]
        One entry per rule that fired, containing rule metadata and the
        specific outcomes it contributed.
    outcomes_applied : dict
        Aggregated totals: ``{"xp": int, "gold": int,
        "achievements": list[str | int]}``.
        ``achievements`` contains template names or IDs from any
        ``achievement`` outcome blocks that fired.
    context_snapshot : dict
        Copy of the context dict used during evaluation.  Stored for
        auditability and the "Why was I rewarded?" explainability view.
    """

    matched_rules: list[dict] = field(default_factory=list)
    outcomes_applied: dict = field(default_factory=dict)
    context_snapshot: dict = field(default_factory=dict)

    # Convenience helpers — populated from outcomes_applied.
    @property
    def achievements_to_dispatch(self) -> list[str | int]:
        """Achievement template names/IDs flagged by rule outcomes."""
        return self.outcomes_applied.get("achievements", [])


# ---------------------------------------------------------------------------
# Outcome processing helpers
# ---------------------------------------------------------------------------


def _process_outcome(
    outcome: dict[str, Any],
    context: dict[str, Any],
) -> tuple[str, int]:
    """Resolve a single outcome definition to a (currency_type, amount) pair.

    Parameters
    ----------
    outcome : dict
        Outcome definition from a rule's ``outcomes`` list.
    context : dict
        The context bucket for this evaluation.

    Returns
    -------
    tuple[str, int]
        ``(outcome_type, amount)`` where ``outcome_type`` is one of
        ``"xp"``, ``"gold"``.
    """
    outcome_type = outcome.get("type", "").lower()
    base_value = float(outcome.get("base_value", 0))
    scaling_config = outcome.get("scaling")

    if scaling_config:
        amount = int(resolve_scaling(base_value, scaling_config, context))
    else:
        amount = int(base_value)

    return outcome_type, max(0, amount)


def _aggregate_outcomes(
    rules_data: list[dict[str, Any]],
    matched_rule_ids: set[int | str],
    context: dict[str, Any],
) -> tuple[list[dict], dict]:
    """Build the matched_rules trace list and aggregate outcome totals.

    Parameters
    ----------
    rules_data : list[dict]
        All rules that passed predicate evaluation.
    matched_rule_ids : set
        IDs of matched rules (for filtering the trace).
    context : dict
        The context bucket used during evaluation.

    Returns
    -------
    tuple[list[dict], dict]
        ``(matched_rules_trace, outcomes_applied)``
    """
    totals: dict[str, Any] = {"xp": 0, "gold": 0, "achievements": []}
    _numeric_keys = {"xp", "gold"}
    matched_trace: list[dict] = []

    for rule in rules_data:
        rule_id = rule.get("id", rule.get("name", "unknown"))
        if rule_id not in matched_rule_ids:
            continue

        rule_outcomes: dict[str, Any] = {}
        for raw_outcome in rule.get("outcomes", []):
            # Achievement outcomes carry a reference, not a numeric amount —
            # handle them before handing off to _process_outcome.
            raw_type = raw_outcome.get("type", "").lower()
            if raw_type == "achievement":
                tmpl_ref = raw_outcome.get("template_name") or raw_outcome.get("template_id")
                if tmpl_ref is not None:
                    totals["achievements"].append(tmpl_ref)
                    rule_outcomes.setdefault("achievements", []).append(tmpl_ref)
                continue

            otype, amount = _process_outcome(raw_outcome, context)
            if otype in _numeric_keys:
                totals[otype] += amount
                rule_outcomes[otype] = rule_outcomes.get(otype, 0) + amount

        matched_trace.append(
            {
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name", ""),
                "priority": rule.get("priority", 50),
                "outcomes": rule_outcomes,
            }
        )

    return matched_trace, totals


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------


class RuleEngine:
    """Pure, stateless rule evaluator.

    All public methods are free of side effects.  The same inputs always
    produce the same outputs; there are no caches, timestamps, or random
    values involved.

    Usage
    -----
    ::

        engine = RuleEngine()
        result = engine.evaluate(event, rules_data, context)
        print(result.outcomes_applied)   # {"xp": 15, "gold": 0}
    """

    def evaluate(
        self,
        event: SynapseEvent,
        rules_data: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> RuleEvaluationResult:
        """Evaluate all active rules against an event.

        Rules are evaluated in descending priority order.  All rules whose
        predicates pass are considered "matched" and their outcomes are
        accumulated.

        Parameters
        ----------
        event : SynapseEvent
            The event to evaluate.  Must have ``metadata`` and ``context``
            populated by the service layer before calling this method.
        rules_data : list[dict]
            Serialised rule definitions.  Each entry must have at minimum:
            ``predicates`` (list of predicate dicts) and ``outcomes``
            (list of outcome dicts).  Optional keys: ``id``, ``name``,
            ``priority``.
        context : dict
            The pre-populated context bucket (from ``event.context`` or
            provided separately).

        Returns
        -------
        RuleEvaluationResult
            Immutable result containing the trace and aggregated totals.
        """
        if not rules_data:
            return RuleEvaluationResult(context_snapshot=dict(context))

        # Sort by priority descending (highest priority fires first)
        sorted_rules = sorted(rules_data, key=lambda r: r.get("priority", 50), reverse=True)

        matched_ids: set[int | str] = set()

        for rule in sorted_rules:
            predicates = rule.get("predicates", [])

            # Empty predicates list = matches everything (catch-all rule)
            if not predicates:
                rule_id = rule.get("id", rule.get("name", "unknown"))
                matched_ids.add(rule_id)
                continue

            try:
                all_pass = all(evaluate_predicate(event, pred) for pred in predicates)
            except Exception:
                logger.debug(
                    "Predicate evaluation error in rule %r (skipped)",
                    rule.get("name", rule.get("id")),
                    exc_info=True,
                )
                continue

            if all_pass:
                rule_id = rule.get("id", rule.get("name", "unknown"))
                matched_ids.add(rule_id)

        if not matched_ids:
            return RuleEvaluationResult(context_snapshot=dict(context))

        matched_trace, totals = _aggregate_outcomes(sorted_rules, matched_ids, context)

        return RuleEvaluationResult(
            matched_rules=matched_trace,
            outcomes_applied=totals,
            context_snapshot=dict(context),
        )
