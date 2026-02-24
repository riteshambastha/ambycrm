"""Recall.ai connector (API key-based bot/transcription platform)."""

import os
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata

_API_KEY = os.getenv("RECALL_API_KEY", "")
_API_URL = "https://us-east-1.recall.ai/api/v1"


class RecallConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="recall",
        name="Recall.ai",
        category="meetings",
        auth_type="api_key",
        scope="org",
        description="Access recordings and transcripts from Zoom, Teams, and Meet via Recall.ai bots.",
        icon_url="/icons/recall.svg",
        oauth_scopes=[],
        oauth_config={},
    )

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?state={state}&connector=recall"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        return {"access_token": code, "token_type": "api_key"}

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return credentials

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_API_URL}/bot/",
                params={"limit": 1},
                headers={"Authorization": f"Token {credentials['access_token']}"},
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_API_URL}/bot/",
                params={"limit": 10},
                headers={"Authorization": f"Token {credentials['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()
            bots = data.get("results", [])
            # Filter by meeting_url or bot_name matching query
            filtered = [
                b for b in bots
                if query.lower() in (b.get("bot_name") or "").lower()
                or query.lower() in (b.get("meeting_url") or "").lower()
            ]
            return {"results": filtered or bots[:5], "source": "recall"}
