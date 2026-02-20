from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapse.services.event_lake_writer import EventLakeWriter


@pytest.fixture
def mock_engine():
    return MagicMock()


@pytest.fixture
def mock_session():
    # Mock the session object and its execute method for updates
    session = MagicMock()
    return session


@pytest.fixture
def writer(mock_engine):
    # Initialize with empty set
    return EventLakeWriter(mock_engine, afk_channel_ids=set())


def test_initial_afk_channels(mock_engine):
    channels = {123, 456}
    writer = EventLakeWriter(mock_engine, afk_channel_ids=channels)
    assert writer.afk_channel_ids == channels


def test_set_afk_channels(writer):
    new_channels = {789, 101}
    writer.set_afk_channels(new_channels)
    assert writer.afk_channel_ids == new_channels


def test_write_voice_join_respects_afk(writer, mock_session):
    # Setup mock get_session context manager
    # We patch at instance level or module level?
    # EventLakeWriter uses `from synapse.database.engine import get_session`.
    # So we must patch `synapse.services.event_lake_writer.get_session`
    pass


# We will use pytest-mock or unittest.mock.patch
# Since we are inside a test file, we can use the `mocker` fixture if available,
# or explicit patch context manager.


def test_afk_logic_integration(writer, mock_engine, mock_session):
    """Verify that joining an AFK channel sets is_afk=True in the payload."""

    # Arrange
    afk_channel_id = 999
    regular_channel_id = 111
    user_id = 100
    guild_id = 1

    writer.set_afk_channels({afk_channel_id})

    # Patched get_session to return our mock session
    with patch("synapse.services.event_lake_writer.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Act 1: Join AFK channel
        writer.write_voice_join(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=afk_channel_id,
            session_id="session_afk",
        )

        # Assert 1
        # Check that session.add was called with an EventLake object
        assert mock_session.add.called
        args, _ = mock_session.add.call_args
        event = args[0]
        assert event.payload["is_afk"] is True
        assert event.payload["channel_id"] == str(afk_channel_id)

        # Act 2: Join Regular Channel
        mock_session.reset_mock()
        writer.write_voice_join(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=regular_channel_id,
            session_id="session_regular",
        )

        # Assert 2
        assert mock_session.add.called
        args, _ = mock_session.add.call_args
        event = args[0]
        assert event.payload["is_afk"] is False
        assert event.payload["channel_id"] == str(regular_channel_id)
