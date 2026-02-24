"""Otter.ai connector (API key-based)."""

import os
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata

_API_URL = "https://api.otter.ai/v1"


class OtterConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="otter",
        name="Otter.ai",
        category="meetings",
        auth_type="api_key",
        scope="user",
        description="Access Otter.ai meeting transcripts and action items.",
        icon_url="/icons/otter.svg",
        oauth_scopes=[],
        oauth_config={},
    )

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?state={state}&connector=otter"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        # code = username:api_key
        username, api_key = code.split(":", 1)
        return {"access_token": api_key, "username": username, "token_type": "api_key"}

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return credentials

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_API_URL}/speeches",
                params={"page_size": 1},
                auth=(credentials.get("username", ""), credentials["access_token"]),
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_API_URL}/speeches",
                params={"page_size": 10},
                auth=(credentials.get("username", ""), credentials["access_token"]),
            )
            resp.raise_for_status()
            data = resp.json()
            speeches = data.get("speeches", [])
            # Filter by title match
            filtered = [s for s in speeches if query.lower() in (s.get("title") or "").lower()]
            return {"results": filtered or speeches[:5], "source": "otter"}
