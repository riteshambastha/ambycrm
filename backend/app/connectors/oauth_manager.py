"""
Generic OAuth2 Authorization Code flow manager.
Connectors call this instead of rolling their own OAuth logic.
"""

import hashlib
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def generate_state(org_id: str, connector_key: str) -> str:
    """Generate a signed state token embedding org + connector info."""
    nonce = secrets.token_urlsafe(16)
    raw = f"{org_id}:{connector_key}:{nonce}"
    return raw


def parse_state(state: str) -> tuple[str, str, str]:
    """Parse a state token. Returns (org_id, connector_key, nonce)."""
    parts = state.split(":", 2)
    if len(parts) != 3:
        raise ValueError("Invalid state token")
    return parts[0], parts[1], parts[2]


def build_authorization_url(
    auth_url: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    extra_params: dict[str, str] | None = None,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        **(extra_params or {}),
    }
    return f"{auth_url}?{urllib.parse.urlencode(params)}"


async def exchange_authorization_code(
    token_url: str,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    extra_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Exchange an auth code for tokens using the standard POST flow."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        **(extra_params or {}),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(
    token_url: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    extra_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Use a refresh token to obtain a new access token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        **(extra_params or {}),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        return resp.json()


def compute_expires_at(expires_in_seconds: int | None) -> datetime | None:
    if expires_in_seconds is None:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
