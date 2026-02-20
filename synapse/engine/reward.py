"""
synapse.engine.reward — Reward Calculation Pipeline
=====================================================

Pure calculation logic for firewall rule outcomes and scaling curves.
No Discord I/O, no DB I/O inside the engine.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from synapse.database.models import ScalingCurve

if TYPE_CHECKING:
    from synapse.engine.events import SynapseEvent

logger = logging.getLogger(__name__)

__all__ = [
    "RewardResult",
    "evaluate_predicate",
    "resolve_scaling",
]


# ---------------------------------------------------------------------------
# Predicate Evaluation (The Firewall Filters)
# ---------------------------------------------------------------------------


def evaluate_predicate(event: SynapseEvent, predicate: dict[str, Any]) -> bool:
    """Evaluate an atomic predicate against a SynapseEvent.

    Example predicate: {"field": "metadata.length", "op": ">=", "value": 100}
    """
    field_path = predicate.get("field", "")
    op = predicate.get("op", "==")
    target_value = predicate.get("value")

    # Resolve actual value from event (support nested metadata/context)
    actual_value = _get_field_value(event, field_path)

    if actual_value is None:
        return False

    try:
        if op == "==":
            return actual_value == target_value
        if op == "!=":
            return actual_value != target_value
        if op == ">":
            return actual_value > target_value
        if op == ">=":
            return actual_value >= target_value
        if op == "<":
            return actual_value < target_value
        if op == "<=":
            return actual_value <= target_value
        if op == "contains":
            return target_value in actual_value
        if op == "not_contains":
            return target_value not in actual_value
    except (TypeError, ValueError):
        return False

    return False


def _get_field_value(event: SynapseEvent, path: str) -> Any | None:
    """Helper to traverse SynapseEvent attributes and dictionaries."""
    parts = path.split(".")
    obj: Any = event

    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            return None
    return obj


# ---------------------------------------------------------------------------
# Scaling Resolution (The Non-Linear Math)
# ---------------------------------------------------------------------------


def resolve_scaling(
    base_value: float, scaling_config: dict[str, Any], context: dict[str, Any]
) -> float:
    """Apply non-linear scaling curves to a base reward value.

    Supported curves: linear, logarithmic, exponential, step.
    N is determined by the configured 'variable' from the context bucket.
    """
    curve = scaling_config.get("curve", ScalingCurve.LINEAR)
    variable_name = scaling_config.get("variable")
    factor = scaling_config.get("factor", 1.0)

    # N is the current value of the variable (e.g. daily_message_count)
    n = context.get(variable_name, 1) if variable_name else 1

    if curve == ScalingCurve.LOGARITHMIC:
        # Avoid log(0)
        return base_value * math.log(max(1, n), scaling_config.get("base", 10)) * factor

    if curve == ScalingCurve.EXPONENTIAL:
        return base_value * math.pow(n, factor)

    if curve == ScalingCurve.STEP:
        thresholds = scaling_config.get("thresholds", {})  # { "10": 1.5, "50": 2.0 }
        # Find highest threshold <= n
        multiplier = 1.0
        for thresh_str, mult in sorted(thresholds.items(), key=lambda x: int(x[0])):
            if n >= int(thresh_str):
                multiplier = mult
        return base_value * multiplier

    # Default to linear
    return base_value * n * factor


# ---------------------------------------------------------------------------
# RewardResult — output of the pipeline
# ---------------------------------------------------------------------------
@dataclass
class RewardResult:
    """Final reward calculation output.

    Attributes
    ----------
    xp : int
        Primary metric for leveling.
    leveled_up : bool
        True if the user reached a new level threshold.
    new_level : int | None
        The user's new level if they leveled up.
    gold_bonus : int
        Secondary currency awarded (economy).
    achievements_earned : list[int]
        IDs of achievement templates granted in this pass.
    """

    xp: int = 0
    leveled_up: bool = False
    new_level: int | None = None
    gold_bonus: int = 0
    achievements_earned: list[int] = field(default_factory=list)
