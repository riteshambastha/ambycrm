"""Fireflies.ai connector (GraphQL API)."""

import os
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata
from app.connectors.oauth_manager import compute_expires_at

_API_KEY = os.getenv("FIREFLIES_API_KEY", "")
_API_URL = "https://api.fireflies.ai/graphql"


class FirefliesConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="fireflies",
        name="Fireflies.ai",
        category="meetings",
        auth_type="api_key",
        scope="user",
        description="Access meeting transcripts and summaries from Fireflies.ai.",
        icon_url="/icons/fireflies.svg",
        oauth_scopes=[],
        oauth_config={},
    )

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        # Fireflies uses API key auth — redirect to settings page
        return f"{redirect_uri}?state={state}&connector=fireflies"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        # `code` carries the API key entered by the user
        return {"access_token": code, "token_type": "api_key"}

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        # API keys don't expire
        return credentials

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        query = """query { user { user_id name email } }"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _API_URL,
                json={"query": query},
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return resp.status_code == 200 and "errors" not in resp.json()

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        """Fetch recent transcripts matching the query."""
        gql = """
        query Transcripts($title: String) {
          transcripts(title: $title) {
            id title date duration
            summary { overview action_items keywords }
            sentences { raw_words speaker_name }
          }
        }
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _API_URL,
                json={"query": gql, "variables": {"title": query[:100]}},
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()
            transcripts = data.get("data", {}).get("transcripts", [])
            return {"results": transcripts, "source": "fireflies"}
