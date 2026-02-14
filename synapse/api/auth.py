"""
synapse.api.auth — Discord OAuth2 + JWT issuance
===================================================
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import delete

from synapse.api.deps import (
    JWT_ALGORITHM,
    JWT_SECRET,
    get_config,
    get_current_admin,
    get_engine,
)
from synapse.config import SynapseConfig
from synapse.database.engine import get_session, run_db
from synapse.database.models import OAuthState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

DISCORD_API = "https://discord.com/api/v10"


def _oauth_env() -> tuple[str, str, str, str]:
    """Return required OAuth env vars or raise a clear 500."""
    client_id = os.getenv("DISCORD_CLIENT_ID", "").strip()
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "").strip()
    frontend_url = os.getenv("FRONTEND_URL", "").strip()

    missing = []
    if not client_id:
        missing.append("DISCORD_CLIENT_ID")
    if not client_secret:
        missing.append("DISCORD_CLIENT_SECRET")
    if not redirect_uri:
        missing.append("DISCORD_REDIRECT_URI")
    if not frontend_url:
        missing.append("FRONTEND_URL")

    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Discord OAuth is not configured: missing "
                + ", ".join(missing)
            ),
        )

    return client_id, client_secret, redirect_uri, frontend_url

OAUTH_STATE_TTL_SECONDS = 600


def _store_oauth_state(engine, state: str) -> None:
    """Persist an OAuth state token and prune stale entries."""
    cutoff = datetime.now(UTC) - timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
    with get_session(engine) as session:
        session.execute(delete(OAuthState).where(OAuthState.created_at < cutoff))
        session.add(OAuthState(state=state))


def _consume_oauth_state(engine, state: str) -> bool:
    """Consume a one-time OAuth state token if valid and unexpired."""
    cutoff = datetime.now(UTC) - timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
    with get_session(engine) as session:
        session.execute(delete(OAuthState).where(OAuthState.created_at < cutoff))
        row = session.get(OAuthState, state)
        if row is None:
            return False
        session.delete(row)
        return True


@router.get("/login")
async def login(engine=Depends(get_engine)):
    """Redirect to Discord OAuth2 consent screen."""
    client_id, _, redirect_uri, _ = _oauth_env()

    state = secrets.token_urlsafe(32)
    await run_db(_store_oauth_state, engine, state)

    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "identify guilds.members.read",
            "state": state,
        }
    )
    url = f"https://discord.com/oauth2/authorize?{query}"
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    cfg: SynapseConfig = Depends(get_config),
    engine=Depends(get_engine),
):
    """Exchange OAuth code for JWT."""
    client_id, client_secret, redirect_uri, frontend_url = _oauth_env()

    # Verify state
    if not await run_db(_consume_oauth_state, engine, state):
        raise HTTPException(400, "Invalid or expired OAuth state")

    # Exchange code for token and fetch user info (single client, explicit timeout + retry)
    transport = httpx.AsyncHTTPTransport(retries=1)
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        token_resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "identify guilds.members.read",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(400, "OAuth token exchange failed")

        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(400, "No access token returned")

        headers = {"Authorization": f"Bearer {access_token}"}

        # Get user info
        user_resp = await client.get(f"{DISCORD_API}/users/@me", headers=headers)
        member_resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds/{cfg.guild_id}/member",
            headers=headers,
        )

    if user_resp.status_code != 200:
        raise HTTPException(400, "Failed to fetch Discord user")

    user_info = user_resp.json()

    # Check admin role
    has_admin = False
    if member_resp.status_code == 200:
        member = member_resp.json()
        role_ids = [int(r) for r in member.get("roles", [])]
        has_admin = cfg.admin_role_id in role_ids

    if not has_admin:
        # Redirect to frontend with error
        return RedirectResponse(f"{frontend_url}?auth_error=not_admin")

    # Issue JWT
    payload = {
        "sub": user_info["id"],
        "username": user_info.get("username", "Unknown"),
        "avatar": user_info.get("avatar"),
        "is_admin": True,
        "exp": datetime.now(UTC) + timedelta(hours=12),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Redirect to frontend with token
    return RedirectResponse(f"{frontend_url}/auth/callback?token={token}")


@router.get("/me")
async def me(admin: dict = Depends(get_current_admin)):
    """Return the current authenticated admin's info."""
    return {
        "id": admin["sub"],
        "username": admin.get("username", "Unknown"),
        "avatar": admin.get("avatar"),
        "is_admin": True,
    }
