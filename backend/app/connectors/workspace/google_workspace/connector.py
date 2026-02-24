"""Google Workspace connector (Gmail + Drive)."""

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

_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleWorkspaceConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="google_workspace",
        name="Google Workspace",
        category="workspace",
        auth_type="oauth2",
        scope="user",
        description="Connect Gmail and Google Drive to search emails and documents.",
        icon_url="/icons/google.svg",
        oauth_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
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
            extra_params={"access_type": "offline", "prompt": "consent"},
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
                "https://www.googleapis.com/oauth2/v1/userinfo",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        """Search Gmail messages matching the query."""
        results = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Search Gmail
            resp = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                params={"q": query[:200], "maxResults": 10},
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            if resp.status_code == 200:
                message_ids = [m["id"] for m in resp.json().get("messages", [])]
                for mid in message_ids[:5]:
                    msg_resp = await client.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                        params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                        headers={"Authorization": f"Bearer {credentials['access_token']}"},
                    )
                    if msg_resp.status_code == 200:
                        results.append(msg_resp.json())
        return {"results": results, "source": "gmail"}
