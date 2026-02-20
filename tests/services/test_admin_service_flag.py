"""
tests.services.test_admin_service_flag — toggle_feature_flag unit tests
========================================================================

Tests the ``admin_service.toggle_feature_flag`` function which provides
the audited create/update path for feature-flag settings rows.  Covered:

- Creates a new Setting row when none exists (action=CREATE)
- Updates an existing Setting row (action=UPDATE)
- AdminLog is written with correct before/after snapshots in both cases
- Calling twice with the same value produces two audit rows (idempotent DB,
  audited each time)
- Enabling then disabling round-trips the value correctly
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from synapse.database.models import AdminLog, Base, Setting
from synapse.services import admin_service

# ---------------------------------------------------------------------------
# SQLite JSONB shim (mirrors conftest.py for isolated test module)
# ---------------------------------------------------------------------------

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # type: ignore[misc]
    return "TEXT"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_FLAG_KEY = "flags.firewall_enabled"
_FLAG_LABEL = "Rule Firewall"
_FLAG_DESC = "Enable after projection workers stable."
_ACTOR_ID = 999


def _call(engine, *, value: bool) -> None:
    """Call toggle_feature_flag with notify patched for SQLite."""
    with patch("synapse.services.admin_service.notify_before_commit"):
        admin_service.toggle_feature_flag(
            engine,
            flag_key=_FLAG_KEY,
            flag_label=_FLAG_LABEL,
            flag_description=_FLAG_DESC,
            new_value=value,
            actor_id=_ACTOR_ID,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToggleFeatureFlagCreate:
    def test_creates_setting_row(self, db_engine):
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            row = session.get(Setting, _FLAG_KEY)
        assert row is not None
        assert row.value_json == "true"

    def test_setting_row_has_correct_category(self, db_engine):
        _call(db_engine, value=False)
        with Session(db_engine) as session:
            row = session.get(Setting, _FLAG_KEY)
        assert row.category == "flags"

    def test_setting_row_has_description(self, db_engine):
        _call(db_engine, value=False)
        with Session(db_engine) as session:
            row = session.get(Setting, _FLAG_KEY)
        assert row.description == _FLAG_DESC

    def test_admin_log_written_on_create(self, db_engine):
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            logs = list(
                session.scalars(
                    select(AdminLog).where(AdminLog.target_id == _FLAG_KEY)
                )
            )
        assert len(logs) == 1
        assert logs[0].action_type == "CREATE"
        assert logs[0].actor_id == _ACTOR_ID
        assert logs[0].target_table == "settings"

    def test_admin_log_before_is_none_on_create(self, db_engine):
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            log = session.scalar(
                select(AdminLog).where(AdminLog.target_id == _FLAG_KEY)
            )
        assert log.before_snapshot is None

    def test_admin_log_after_snapshot_correct_on_create(self, db_engine):
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            log = session.scalar(
                select(AdminLog).where(AdminLog.target_id == _FLAG_KEY)
            )
        assert log.after_snapshot == {"key": _FLAG_KEY, "value": True}


class TestToggleFeatureFlagUpdate:
    def test_updates_existing_setting(self, db_engine):
        _call(db_engine, value=False)
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            row = session.get(Setting, _FLAG_KEY)
        assert row.value_json == "true"

    def test_admin_log_written_on_update(self, db_engine):
        _call(db_engine, value=False)
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            logs = list(
                session.scalars(
                    select(AdminLog)
                    .where(AdminLog.target_id == _FLAG_KEY)
                    .order_by(AdminLog.id)
                )
            )
        assert len(logs) == 2
        assert logs[1].action_type == "UPDATE"

    def test_admin_log_before_snapshot_on_update(self, db_engine):
        _call(db_engine, value=False)
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            logs = list(
                session.scalars(
                    select(AdminLog)
                    .where(AdminLog.target_id == _FLAG_KEY)
                    .order_by(AdminLog.id)
                )
            )
        # Second log is the UPDATE; before should show False
        assert logs[1].before_snapshot == {"key": _FLAG_KEY, "value": False}

    def test_admin_log_after_snapshot_on_update(self, db_engine):
        _call(db_engine, value=False)
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            logs = list(
                session.scalars(
                    select(AdminLog)
                    .where(AdminLog.target_id == _FLAG_KEY)
                    .order_by(AdminLog.id)
                )
            )
        assert logs[1].after_snapshot == {"key": _FLAG_KEY, "value": True}


class TestToggleFeatureFlagRoundtrip:
    def test_enable_then_disable(self, db_engine):
        _call(db_engine, value=True)
        _call(db_engine, value=False)
        with Session(db_engine) as session:
            row = session.get(Setting, _FLAG_KEY)
        assert row.value_json == "false"

    def test_three_audit_rows_for_three_calls(self, db_engine):
        _call(db_engine, value=True)
        _call(db_engine, value=False)
        _call(db_engine, value=True)
        with Session(db_engine) as session:
            logs = list(
                session.scalars(
                    select(AdminLog).where(AdminLog.target_id == _FLAG_KEY)
                )
            )
        assert len(logs) == 3
