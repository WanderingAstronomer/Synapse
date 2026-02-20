"""
tests.test_phase6_media — Phase 6: Media Library v2 Tests
==========================================================

Tests media_service folder CRUD and SVG overlay seeder, and the
updated media API routes (folder endpoints + folder_id on upload/update).

No real database, no Docker, no Discord required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapse.services.media_service import (
    _DEFAULT_OVERLAYS,
    create_folder,
    delete_folder_if_empty,
    list_folders,
    rename_folder,
    seed_svg_overlays,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_ctx(session_obj):
    """Wrap a MagicMock session so `with Session(engine) as s:` works."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session_obj)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_folder(id_: int, guild_id: int, name: str, parent_id=None):
    from synapse.database.models import MediaFolder

    f = MagicMock(spec=MediaFolder)
    f.id = id_
    f.guild_id = guild_id
    f.name = name
    f.parent_id = parent_id
    f.created_at = None
    return f


# ---------------------------------------------------------------------------
# create_folder
# ---------------------------------------------------------------------------


class TestCreateFolder:
    def _session(self, parent=None):
        mock = MagicMock()
        mock.get.return_value = parent
        return mock

    def test_creates_folder_no_parent(self):
        engine = MagicMock()
        session = self._session()

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            create_folder(engine, 1111, "Badges")

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.guild_id == 1111
        assert added.name == "Badges"
        assert added.parent_id is None
        session.commit.assert_called_once()

    def test_creates_folder_with_valid_parent(self):
        engine = MagicMock()
        parent = _make_folder(5, 1111, "Root")
        session = self._session(parent=parent)

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            create_folder(engine, 1111, "Sub", parent_id=5)

        added = session.add.call_args[0][0]
        assert added.parent_id == 5

    def test_raises_when_parent_not_found(self):
        engine = MagicMock()
        session = self._session(parent=None)

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="not found"):
                create_folder(engine, 1111, "Sub", parent_id=999)

    def test_raises_when_parent_belongs_to_different_guild(self):
        engine = MagicMock()
        other_guild_parent = _make_folder(5, 9999, "Root")
        session = self._session(parent=other_guild_parent)

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="not found"):
                create_folder(engine, 1111, "Sub", parent_id=5)

    def test_raises_on_name_collision(self):
        from sqlalchemy.exc import IntegrityError

        engine = MagicMock()
        session = self._session()
        session.commit.side_effect = IntegrityError("dup", None, None)

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="already exists"):
                create_folder(engine, 1111, "Badges")


# ---------------------------------------------------------------------------
# rename_folder
# ---------------------------------------------------------------------------


class TestRenameFolder:
    def test_renames_successfully(self):
        engine = MagicMock()
        folder = _make_folder(10, 1111, "Old Name")
        session = MagicMock()
        session.get.return_value = folder

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            rename_folder(engine, 10, 1111, "New Name")

        assert folder.name == "New Name"
        session.commit.assert_called_once()

    def test_raises_when_folder_not_found(self):
        engine = MagicMock()
        session = MagicMock()
        session.get.return_value = None

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="not found"):
                rename_folder(engine, 99, 1111, "New Name")

    def test_raises_when_folder_belongs_to_different_guild(self):
        engine = MagicMock()
        folder = _make_folder(10, 9999, "Name")
        session = MagicMock()
        session.get.return_value = folder

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="not found"):
                rename_folder(engine, 10, 1111, "New Name")

    def test_raises_on_name_collision(self):
        from sqlalchemy.exc import IntegrityError

        engine = MagicMock()
        folder = _make_folder(10, 1111, "Old")
        session = MagicMock()
        session.get.return_value = folder
        session.commit.side_effect = IntegrityError("dup", None, None)

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="already exists"):
                rename_folder(engine, 10, 1111, "Existing Name")


# ---------------------------------------------------------------------------
# delete_folder_if_empty
# ---------------------------------------------------------------------------


class TestDeleteFolderIfEmpty:
    def test_deletes_empty_folder(self):
        engine = MagicMock()
        folder = _make_folder(20, 1111, "Empty")
        session = MagicMock()
        session.get.return_value = folder
        # scalar returns 0 for both file_count and child_count
        session.scalar.return_value = 0

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            delete_folder_if_empty(engine, 20, 1111)

        session.delete.assert_called_once_with(folder)
        session.commit.assert_called_once()

    def test_raises_when_folder_has_files(self):
        engine = MagicMock()
        folder = _make_folder(20, 1111, "Has Files")
        session = MagicMock()
        session.get.return_value = folder
        # First scalar call returns file count = 3
        session.scalar.return_value = 3

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="3 file"):
                delete_folder_if_empty(engine, 20, 1111)

        session.delete.assert_not_called()

    def test_raises_when_folder_has_subfolders(self):
        engine = MagicMock()
        folder = _make_folder(20, 1111, "Has Children")
        session = MagicMock()
        session.get.return_value = folder
        # First call (file count) = 0, second call (child count) = 2
        session.scalar.side_effect = [0, 2]

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="sub-folder"):
                delete_folder_if_empty(engine, 20, 1111)

    def test_raises_when_folder_not_found(self):
        engine = MagicMock()
        session = MagicMock()
        session.get.return_value = None

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="not found"):
                delete_folder_if_empty(engine, 99, 1111)

    def test_raises_when_folder_belongs_to_different_guild(self):
        engine = MagicMock()
        folder = _make_folder(20, 9999, "Other Guild")
        session = MagicMock()
        session.get.return_value = folder

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            with pytest.raises(ValueError, match="not found"):
                delete_folder_if_empty(engine, 20, 1111)


# ---------------------------------------------------------------------------
# list_folders
# ---------------------------------------------------------------------------


class TestListFolders:
    def test_returns_folders_for_guild(self):
        engine = MagicMock()
        f1 = _make_folder(1, 1111, "A")
        f2 = _make_folder(2, 1111, "B")
        session = MagicMock()
        session.scalars.return_value.all.return_value = [f1, f2]

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            result = list_folders(engine, 1111)

        assert result == [f1, f2]

    def test_returns_empty_list_when_no_folders(self):
        engine = MagicMock()
        session = MagicMock()
        session.scalars.return_value.all.return_value = []

        with patch(
            "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
        ):
            result = list_folders(engine, 1111)

        assert result == []


# ---------------------------------------------------------------------------
# seed_svg_overlays
# ---------------------------------------------------------------------------


class TestSeedSvgOverlays:
    def test_creates_all_four_default_overlays_on_empty_db(self, tmp_path):
        engine = MagicMock()
        session = MagicMock()
        # scalar returns None for every "existing?" query → all are new
        session.scalar.return_value = None

        with (
            patch(
                "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
            ),
            patch("synapse.services.media_service.UPLOAD_DIR", tmp_path),
        ):
            count = seed_svg_overlays(engine, 1111)

        assert count == 4
        assert session.add.call_count == 4
        session.commit.assert_called_once()
        # All four SVG files should have been written
        for name in _DEFAULT_OVERLAYS:
            assert (tmp_path / f"default_{name}.svg").exists()

    def test_idempotent_when_all_exist(self, tmp_path):
        engine = MagicMock()
        session = MagicMock()
        # All SVG files exist on disk, all records exist in DB
        for name in _DEFAULT_OVERLAYS:
            (tmp_path / f"default_{name}.svg").write_text("<svg/>")
        # scalar returns a truthy SvgOverlay mock for each query
        from synapse.database.models import SvgOverlay

        session.scalar.return_value = MagicMock(spec=SvgOverlay)

        with (
            patch(
                "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
            ),
            patch("synapse.services.media_service.UPLOAD_DIR", tmp_path),
        ):
            count = seed_svg_overlays(engine, 1111)

        assert count == 0
        session.add.assert_not_called()

    def test_partial_seed_creates_only_missing(self, tmp_path):
        """Two records already exist  →  only two new ones created."""
        engine = MagicMock()
        session = MagicMock()
        from synapse.database.models import SvgOverlay

        existing = MagicMock(spec=SvgOverlay)
        # First two queries return existing record, last two return None
        session.scalar.side_effect = [existing, existing, None, None]

        with (
            patch(
                "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
            ),
            patch("synapse.services.media_service.UPLOAD_DIR", tmp_path),
        ):
            count = seed_svg_overlays(engine, 1111)

        assert count == 2

    def test_svg_url_format(self, tmp_path):
        """Each seeded overlay must reference /api/uploads/default_<name>.svg."""
        engine = MagicMock()
        session = MagicMock()
        session.scalar.return_value = None
        added_overlays = []

        def capture_add(obj):
            added_overlays.append(obj)

        session.add.side_effect = capture_add

        with (
            patch(
                "synapse.services.media_service.Session", return_value=_mock_session_ctx(session)
            ),
            patch("synapse.services.media_service.UPLOAD_DIR", tmp_path),
        ):
            seed_svg_overlays(engine, 1111)

        for overlay in added_overlays:
            assert overlay.svg_url.startswith("/api/uploads/default_border_")
            assert overlay.is_default is True
            assert overlay.guild_id == 1111

    def test_default_overlay_names(self):
        """Verify the expected four default overlay names are defined."""
        expected = {"border_common", "border_rare", "border_epic", "border_legendary"}
        assert set(_DEFAULT_OVERLAYS.keys()) == expected


# ---------------------------------------------------------------------------
# Media API routes — folder CRUD
# ---------------------------------------------------------------------------


class TestMediaFolderRoutes:
    """Unit tests for route handlers by calling them directly with mocked deps."""

    def _deps(self, guild_id: int = 1111):
        engine = MagicMock()
        admin = {"user_id": 1, "is_admin": True}
        cfg = MagicMock()
        cfg.guild_id = guild_id
        return engine, admin, cfg

    def test_list_folders_route_returns_serialized(self):
        from synapse.api.routes.media import list_media_folders

        engine, admin, cfg = self._deps()
        f1 = _make_folder(1, 1111, "Badges")
        f2 = _make_folder(2, 1111, "Borders")

        with patch("synapse.api.routes.media.list_folders", return_value=[f1, f2]):
            result = list_media_folders(engine=engine, admin=admin, cfg=cfg)

        assert len(result["folders"]) == 2
        assert result["folders"][0]["name"] == "Badges"
        assert result["folders"][1]["name"] == "Borders"

    def test_create_folder_route_returns_201_shape(self):
        from synapse.api.routes.media import FolderCreate, create_media_folder

        engine, admin, cfg = self._deps()
        created = _make_folder(7, 1111, "New Folder")

        with patch("synapse.api.routes.media.create_folder", return_value=created):
            result = create_media_folder(
                body=FolderCreate(name="New Folder"), engine=engine, admin=admin, cfg=cfg
            )

        assert result["id"] == 7
        assert result["name"] == "New Folder"
        assert result["parent_id"] is None

    def test_create_folder_route_conflict_raises_409(self):
        from fastapi import HTTPException

        from synapse.api.routes.media import FolderCreate, create_media_folder

        engine, admin, cfg = self._deps()

        with patch(
            "synapse.api.routes.media.create_folder", side_effect=ValueError("already exists")
        ):
            with pytest.raises(HTTPException) as exc_info:
                create_media_folder(
                    body=FolderCreate(name="Dup"), engine=engine, admin=admin, cfg=cfg
                )

        assert exc_info.value.status_code == 409

    def test_rename_folder_route_success(self):
        from synapse.api.routes.media import FolderRename, rename_media_folder

        engine, admin, cfg = self._deps()
        renamed = _make_folder(5, 1111, "Renamed")

        with patch("synapse.api.routes.media.rename_folder", return_value=renamed):
            result = rename_media_folder(
                folder_id=5, body=FolderRename(name="Renamed"), engine=engine, admin=admin, cfg=cfg
            )

        assert result["name"] == "Renamed"

    def test_rename_folder_route_not_found_raises_404(self):
        from fastapi import HTTPException

        from synapse.api.routes.media import FolderRename, rename_media_folder

        engine, admin, cfg = self._deps()

        with patch("synapse.api.routes.media.rename_folder", side_effect=ValueError("not found")):
            with pytest.raises(HTTPException) as exc_info:
                rename_media_folder(
                    folder_id=99, body=FolderRename(name="X"), engine=engine, admin=admin, cfg=cfg
                )

        assert exc_info.value.status_code == 404

    def test_delete_folder_route_success(self):
        from synapse.api.routes.media import delete_media_folder

        engine, admin, cfg = self._deps()

        with patch("synapse.api.routes.media.delete_folder_if_empty", return_value=None):
            # Returns None (204) — should not raise
            result = delete_media_folder(folder_id=5, engine=engine, admin=admin, cfg=cfg)
        assert result is None

    def test_delete_folder_route_not_empty_raises_409(self):
        from fastapi import HTTPException

        from synapse.api.routes.media import delete_media_folder

        engine, admin, cfg = self._deps()

        with patch(
            "synapse.api.routes.media.delete_folder_if_empty",
            side_effect=ValueError("contains 3 file(s)"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                delete_media_folder(folder_id=5, engine=engine, admin=admin, cfg=cfg)

        assert exc_info.value.status_code == 409

    def test_delete_folder_route_not_found_raises_404(self):
        from fastapi import HTTPException

        from synapse.api.routes.media import delete_media_folder

        engine, admin, cfg = self._deps()

        with patch(
            "synapse.api.routes.media.delete_folder_if_empty",
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                delete_media_folder(folder_id=99, engine=engine, admin=admin, cfg=cfg)

        assert exc_info.value.status_code == 404

    def test_list_media_route_includes_folder_id(self):
        """list_media response items must include folder_id."""
        from sqlalchemy.orm import Session as SaSession

        from synapse.api.routes.media import list_media
        from synapse.database.models import MediaFile

        session = MagicMock(spec=SaSession)
        file_mock = MagicMock(spec=MediaFile)
        file_mock.id = 1
        file_mock.url = "/api/uploads/test.png"
        file_mock.original_name = "test.png"
        file_mock.content_type = "image/png"
        file_mock.size_bytes = 1024
        file_mock.alt_text = None
        file_mock.folder_id = 3
        file_mock.uploaded_at = None
        session.scalars.return_value.all.return_value = [file_mock]

        cfg = MagicMock()
        cfg.guild_id = 1111
        admin = {"user_id": 1}

        result = list_media(folder_id=None, session=session, admin=admin, cfg=cfg)
        assert result["files"][0]["folder_id"] == 3
