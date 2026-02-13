"""
tests/test_jwt_startup — JWT Secret Validation at Startup
===========================================================
Verifies F-003: The API must refuse to start when JWT_SECRET is missing,
blank, too short, or a known weak default.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest


class TestJWTSecretValidation:
    """Prove that _load_jwt_secret() rejects bad secrets and accepts good ones."""

    def _call_load(self) -> str:
        """Re-import the validator so it runs fresh against patched env."""
        # We must reload the module to re-trigger _load_jwt_secret()
        import synapse.api.deps as deps_mod
        importlib.reload(deps_mod)
        return deps_mod.JWT_SECRET

    def test_rejects_missing_secret(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JWT_SECRET", None)
            with pytest.raises(RuntimeError, match="JWT_SECRET environment variable is not set"):
                self._call_load()

    def test_rejects_empty_secret(self):
        with patch.dict(os.environ, {"JWT_SECRET": ""}):
            with pytest.raises(RuntimeError, match="JWT_SECRET environment variable is not set"):
                self._call_load()

    def test_rejects_known_weak_default(self):
        with patch.dict(os.environ, {"JWT_SECRET": "synapse-dev-secret-change-me"}):
            with pytest.raises(RuntimeError, match="known weak default"):
                self._call_load()

    def test_rejects_short_secret(self):
        with patch.dict(os.environ, {"JWT_SECRET": "tooshort"}):
            with pytest.raises(RuntimeError, match="too short"):
                self._call_load()

    def test_accepts_strong_secret(self):
        good_secret = "a" * 64
        with patch.dict(os.environ, {"JWT_SECRET": good_secret}):
            result = self._call_load()
            assert result == good_secret

    def test_rejects_change_me_variant(self):
        with patch.dict(os.environ, {"JWT_SECRET": "change-me"}):
            with pytest.raises(RuntimeError, match="known weak default"):
                self._call_load()

    @pytest.fixture(autouse=True)
    def _restore_jwt_secret(self):
        """Ensure JWT_SECRET is restored after each test so other tests work."""
        original = os.environ.get("JWT_SECRET")
        yield
        if original is not None:
            os.environ["JWT_SECRET"] = original
        else:
            os.environ.pop("JWT_SECRET", None)
        # Reload with restored secret so subsequent module imports work
        import synapse.api.deps as deps_mod
        try:
            importlib.reload(deps_mod)
        except RuntimeError:
            pass  # test env may not have a valid secret set yet
