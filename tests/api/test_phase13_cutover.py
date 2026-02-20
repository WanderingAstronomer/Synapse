"""
tests.api.test_phase13_cutover — Phase 13: Feature Flag Cutover Tests
======================================================================

Tests the cutover status and toggle endpoints:
- Flag ordering enforcement
- Prerequisite validation
- Preflight check gating
- Toggle (enable/disable) with audit logging
- Rollback always allowed

All tests are mock-based — no real database, no Docker required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from synapse.api.routes.cutover import (
    _FLAG_DEFS,
    _FLAG_KEYS,
    _auth_monitoring,
    _auth_preflight,
    _check_disable_dependents,
    _firewall_monitoring,
    _firewall_preflight,
    _flag_enabled_at,
    _marketplace_monitoring,
    _marketplace_preflight,
    _projection_monitoring,
    _projection_preflight,
    _read_flag,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_setting(key: str, value: bool) -> MagicMock:
    """Create a mock Setting row."""
    s = MagicMock()
    s.key = key
    s.value_json = json.dumps(value)
    s.category = "flags"
    s.description = f"Test flag: {key}"
    return s


def _mock_session(settings: dict[str, bool] | None = None) -> MagicMock:
    """Create a mock session that returns settings by key."""
    session = MagicMock()
    _settings = settings or {}

    def _get(model_class, key):
        if key in _settings:
            return _make_setting(key, _settings[key])
        return None

    session.get.side_effect = _get
    return session


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.guild_id = "12345"
    return cfg


# ---------------------------------------------------------------------------
# _read_flag
# ---------------------------------------------------------------------------


class TestReadFlag:
    def test_returns_false_when_missing(self):
        session = MagicMock()
        session.get.return_value = None
        assert _read_flag(session, "flags.nonexistent") is False

    def test_returns_true_when_enabled(self):
        session = MagicMock()
        setting = MagicMock()
        setting.value_json = json.dumps(True)
        session.get.return_value = setting
        assert _read_flag(session, "flags.test") is True

    def test_returns_false_when_disabled(self):
        session = MagicMock()
        setting = MagicMock()
        setting.value_json = json.dumps(False)
        session.get.return_value = setting
        assert _read_flag(session, "flags.test") is False

    def test_returns_false_on_invalid_json(self):
        session = MagicMock()
        setting = MagicMock()
        setting.value_json = "not-json"
        session.get.return_value = setting
        assert _read_flag(session, "flags.test") is False

    def test_returns_false_for_non_boolean(self):
        session = MagicMock()
        setting = MagicMock()
        setting.value_json = json.dumps("yes")
        session.get.return_value = setting
        assert _read_flag(session, "flags.test") is False


# ---------------------------------------------------------------------------
# Flag definitions
# ---------------------------------------------------------------------------


class TestFlagDefinitions:
    def test_four_flags_defined(self):
        assert len(_FLAG_DEFS) == 4

    def test_ordered_1_to_4(self):
        orders = [f["order"] for f in _FLAG_DEFS]
        assert orders == [1, 2, 3, 4]

    def test_all_keys_start_with_flags_prefix(self):
        for f in _FLAG_DEFS:
            assert f["key"].startswith("flags.")

    def test_prerequisite_chain(self):
        """Each flag after the first requires the previous flag."""
        assert _FLAG_DEFS[0]["prerequisites"] == []
        assert _FLAG_DEFS[1]["prerequisites"] == ["flags.projection_workers_enabled"]
        assert _FLAG_DEFS[2]["prerequisites"] == ["flags.firewall_enabled"]
        assert _FLAG_DEFS[3]["prerequisites"] == ["flags.three_tier_auth_enabled"]


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


class TestProjectionPreflight:
    def test_passes_when_evaluations_exist(self):
        session = MagicMock()
        session.scalar.return_value = 10
        cfg = _mock_config()
        checks = _projection_preflight(session, cfg)
        assert len(checks) >= 1
        assert all(c.passed for c in checks)

    def test_fails_when_no_evaluations(self):
        session = MagicMock()
        session.scalar.return_value = 0
        cfg = _mock_config()
        checks = _projection_preflight(session, cfg)
        assert any(not c.passed for c in checks)


class TestFirewallPreflight:
    def test_passes_when_projection_enabled(self):
        session = MagicMock()
        # XP queries return reasonable values
        session.scalar.side_effect = [100, 2400]
        flags = {"flags.projection_workers_enabled": True}
        checks = _firewall_preflight(session, flags)
        assert len(checks) >= 2
        assert checks[0].passed  # projection workers enabled

    def test_fails_when_projection_disabled(self):
        session = MagicMock()
        session.scalar.side_effect = [100, 2400]
        flags = {"flags.projection_workers_enabled": False}
        checks = _firewall_preflight(session, flags)
        assert not checks[0].passed

    def test_fails_when_xp_ratio_high(self):
        session = MagicMock()
        # XP last hour = 5000, XP 24h = 2400 → avg 100/h → ratio 50x
        session.scalar.side_effect = [5000, 2400]
        flags = {"flags.projection_workers_enabled": True}
        checks = _firewall_preflight(session, flags)
        xp_check = checks[1]  # Second check is XP ratio
        assert not xp_check.passed


class TestAuthPreflight:
    def test_passes_when_firewall_enabled(self):
        flags = {"flags.firewall_enabled": True}
        checks = _auth_preflight(flags)
        assert len(checks) >= 1
        assert checks[0].passed

    def test_fails_when_firewall_disabled(self):
        flags = {"flags.firewall_enabled": False}
        checks = _auth_preflight(flags)
        assert not checks[0].passed


class TestMarketplacePreflight:
    def test_passes_when_auth_enabled(self):
        flags = {"flags.three_tier_auth_enabled": True}
        checks = _marketplace_preflight(flags)
        assert len(checks) >= 1
        assert checks[0].passed

    def test_fails_when_auth_disabled(self):
        flags = {"flags.three_tier_auth_enabled": False}
        checks = _marketplace_preflight(flags)
        assert not checks[0].passed


# ---------------------------------------------------------------------------
# Monitoring helpers
# ---------------------------------------------------------------------------


class TestProjectionMonitoring:
    def test_healthy_when_low_lag(self):
        session = MagicMock()
        cp = MagicMock()
        cp.worker_id = "w1"
        cp.last_processed_evaluation_id = 995
        cp.updated_at = datetime.now(UTC)
        session.scalars.return_value = [cp]
        session.scalar.return_value = 1000  # latest eval id
        cfg = _mock_config()
        result = _projection_monitoring(session, cfg)
        assert result.status == "healthy"

    def test_unknown_when_no_workers(self):
        session = MagicMock()
        session.scalars.return_value = []
        session.scalar.return_value = 0
        cfg = _mock_config()
        result = _projection_monitoring(session, cfg)
        assert result.status == "unknown"


class TestFirewallMonitoring:
    def test_healthy_when_normal_rate(self):
        session = MagicMock()
        # xp_last_hour, xp_24h, evals_last_hour
        session.scalar.side_effect = [100, 2400, 50]
        result = _firewall_monitoring(session)
        assert result.status == "healthy"

    def test_critical_when_doubled(self):
        session = MagicMock()
        # xp_last_hour = 500, xp_24h = 2400 → avg 100 → ratio 5x
        session.scalar.side_effect = [500, 2400, 50]
        result = _firewall_monitoring(session)
        assert result.status == "critical"


class TestAuthMonitoring:
    def test_returns_healthy(self):
        session = MagicMock()
        session.scalar.return_value = 3
        result = _auth_monitoring(session)
        assert result.status == "healthy"
        assert result.metrics["auth_events_last_hour"] == 3


class TestMarketplaceMonitoring:
    def test_returns_healthy(self):
        session = MagicMock()
        session.scalar.return_value = 5
        result = _marketplace_monitoring(session)
        assert result.status == "healthy"
        assert result.metrics["purchases_24h"] == 5


# ---------------------------------------------------------------------------
# Flag enabled_at lookup
# ---------------------------------------------------------------------------


class TestFlagEnabledAt:
    def test_returns_timestamp_when_found(self):
        session = MagicMock()
        ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_row = MagicMock()
        mock_row.timestamp = ts
        session.execute.return_value.first.return_value = mock_row
        result = _flag_enabled_at(session, "flags.test")
        assert result == ts.isoformat()

    def test_returns_none_when_not_found(self):
        session = MagicMock()
        session.execute.return_value.first.return_value = None
        result = _flag_enabled_at(session, "flags.test")
        assert result is None


# ---------------------------------------------------------------------------
# Integration: ordering enforcement
# ---------------------------------------------------------------------------


class TestCutoverOrdering:
    """Test that flag ordering is enforced through prerequisites."""

    def test_first_flag_has_no_prerequisites(self):
        """Projection workers can be enabled without any other flag."""
        first = _FLAG_DEFS[0]
        assert first["key"] == "flags.projection_workers_enabled"
        assert first["prerequisites"] == []

    def test_firewall_requires_projection(self):
        fw = _FLAG_DEFS[1]
        assert "flags.projection_workers_enabled" in fw["prerequisites"]

    def test_auth_requires_firewall(self):
        auth = _FLAG_DEFS[2]
        assert "flags.firewall_enabled" in auth["prerequisites"]

    def test_marketplace_requires_auth(self):
        mp = _FLAG_DEFS[3]
        assert "flags.three_tier_auth_enabled" in mp["prerequisites"]

    def test_enable_second_without_first_blocked(self):
        """Attempting to enable firewall without projection should fail preflight."""
        session = MagicMock()
        session.scalar.side_effect = [100, 2400]
        flag_states = {"flags.projection_workers_enabled": False}
        checks = _firewall_preflight(session, flag_states)
        # The prerequisite check should fail
        prereq_check = next(c for c in checks if "Projection" in c.label)
        assert not prereq_check.passed


class TestFlagKeys:
    def test_flag_keys_list_matches_defs(self):
        assert _FLAG_KEYS == [f["key"] for f in _FLAG_DEFS]

    def test_all_known_flags_in_set(self):
        expected = {
            "flags.projection_workers_enabled",
            "flags.firewall_enabled",
            "flags.three_tier_auth_enabled",
            "flags.marketplace_enabled",
        }
        assert set(_FLAG_KEYS) == expected


# ---------------------------------------------------------------------------
# _check_disable_dependents (P13-03)
# ---------------------------------------------------------------------------


class TestCheckDisableDependents:
    """P13-03: Disabling a flag that has dependents still enabled must be blocked."""

    # Convenience: the four flag keys in order
    _PROJ = "flags.projection_workers_enabled"
    _FIRE = "flags.firewall_enabled"
    _AUTH = "flags.three_tier_auth_enabled"
    _MARK = "flags.marketplace_enabled"

    def test_no_dependents_when_all_disabled(self):
        flag_states = {self._PROJ: False, self._FIRE: False, self._AUTH: False, self._MARK: False}
        assert _check_disable_dependents(self._PROJ, flag_states) == []

    def test_returns_empty_when_disabling_last_flag(self):
        """marketplace has no flags that depend on it."""
        flag_states = {self._PROJ: True, self._FIRE: True, self._AUTH: True, self._MARK: True}
        assert _check_disable_dependents(self._MARK, flag_states) == []

    def test_blocks_disabling_projection_when_firewall_enabled(self):
        flag_states = {self._PROJ: True, self._FIRE: True, self._AUTH: False, self._MARK: False}
        result = _check_disable_dependents(self._PROJ, flag_states)
        assert len(result) == 1
        # Result should name the firewall flag's label, not its key
        assert any("Firewall" in label or "firewall" in label.lower() for label in result)

    def test_blocks_disabling_firewall_when_auth_enabled(self):
        flag_states = {self._PROJ: True, self._FIRE: True, self._AUTH: True, self._MARK: False}
        result = _check_disable_dependents(self._FIRE, flag_states)
        assert len(result) == 1

    def test_blocks_disabling_auth_when_marketplace_enabled(self):
        flag_states = {self._PROJ: True, self._FIRE: True, self._AUTH: True, self._MARK: True}
        result = _check_disable_dependents(self._AUTH, flag_states)
        assert len(result) == 1

    def test_safe_to_disable_projection_when_firewall_is_off(self):
        """Even if projection is on, if firewall is off there is no blocker."""
        flag_states = {self._PROJ: True, self._FIRE: False, self._AUTH: False, self._MARK: False}
        assert _check_disable_dependents(self._PROJ, flag_states) == []

    def test_safe_to_disable_firewall_when_auth_is_off(self):
        flag_states = {self._PROJ: True, self._FIRE: True, self._AUTH: False, self._MARK: False}
        assert _check_disable_dependents(self._FIRE, flag_states) == []

    def test_returns_list_not_single_item(self):
        """Return type is always a list."""
        flag_states = {self._PROJ: False, self._FIRE: False, self._AUTH: False, self._MARK: False}
        result = _check_disable_dependents(self._MARK, flag_states)
        assert isinstance(result, list)
