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
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import jwt

from synapse.api.deps import JWT_ALGORITHM, JWT_SECRET, get_config, get_current_admin
from synapse.config import SynapseConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

DISCORD_API = "https://discord.com/api/v10"
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5173/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# In-memory state store (fine for single-instance; swap for Redis at scale)
_pending_states: dict[str, float] = {}


@router.get("/login")
async def login():
    """Redirect to Discord OAuth2 consent screen."""
    state = secrets.token_urlsafe(32)
    _pending_states[state] = datetime.now(UTC).timestamp()
    # Cleanup stale states (> 10 min)
    cutoff = datetime.now(UTC).timestamp() - 600
    for k in [k for k, v in _pending_states.items() if v < cutoff]:
        _pending_states.pop(k, None)

    query = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
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
):
    """Exchange OAuth code for JWT."""
    # Verify state
    if state not in _pending_states:
        raise HTTPException(400, "Invalid or expired OAuth state")
    _pending_states.pop(state, None)

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
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
    async with httpx.AsyncClient() as client:
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
        return RedirectResponse(f"{FRONTEND_URL}?auth_error=not_admin")

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
    return RedirectResponse(f"{FRONTEND_URL}/auth/callback?token={token}")


@router.get("/me")
async def me(admin: dict = Depends(get_current_admin)):
    """Return the current authenticated admin's info."""
    return {
        "id": admin["sub"],
        "username": admin.get("username", "Unknown"),
        "avatar": admin.get("avatar"),
        "is_admin": True,
    }
