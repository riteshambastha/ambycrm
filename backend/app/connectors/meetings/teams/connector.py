"""Microsoft Teams connector (via Graph API)."""

import os
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata
from app.connectors.oauth_manager import (
    build_authorization_url,
    compute_expires_at,
    exchange_authorization_code,
    refresh_access_token,
)

_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
_AUTH_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/authorize"
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token"
_GRAPH_URL = "https://graph.microsoft.com/v1.0"


class TeamsConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="teams",
        name="Microsoft Teams",
        category="meetings",
        auth_type="oauth2",
        scope="user",
        description="Access Teams meeting recordings and transcripts via Microsoft Graph.",
        icon_url="/icons/teams.svg",
        oauth_scopes=[
            "OnlineMeetings.Read",
            "CallRecords.Read.All",
            "User.Read",
            "offline_access",
        ],
        oauth_config={"auth_url": _AUTH_URL, "token_url": _TOKEN_URL},
    )

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        return build_authorization_url(
            auth_url=_AUTH_URL,
            client_id=_CLIENT_ID,
            redirect_uri=redirect_uri,
            scopes=self.metadata.oauth_scopes,
            state=state,
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        tokens = await exchange_authorization_code(
            token_url=_TOKEN_URL,
            code=code,
            client_id=_CLIENT_ID,
            client_secret=_CLIENT_SECRET,
            redirect_uri=redirect_uri,
        )
        tokens["expires_at"] = compute_expires_at(tokens.get("expires_in"))
        return tokens

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        tokens = await refresh_access_token(
            token_url=_TOKEN_URL,
            refresh_token=credentials["refresh_token"],
            client_id=_CLIENT_ID,
            client_secret=_CLIENT_SECRET,
        )
        tokens["expires_at"] = compute_expires_at(tokens.get("expires_in"))
        return tokens

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/me",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/me/onlineMeetings",
                params={"$top": 10},
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"results": data.get("value", []), "source": "teams"}
