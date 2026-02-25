"""
Microsoft 365 connector — Org-level application permissions.

Uses the OAuth 2.0 Client Credentials flow (no user sign-in required).
Requires the Azure AD app to have Application permissions:
  - Mail.Read
  - Mail.ReadBasic.All
  - User.Read.All

The admin must grant tenant-wide admin consent in the Azure portal.
Once connected, the AI service can query any employee's mailbox by email.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata

_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token"
_GRAPH_URL = "https://graph.microsoft.com/v1.0"

# Application-level scope (no user context)
_APP_SCOPE = "https://graph.microsoft.com/.default"


class Microsoft365Connector(BaseConnector):
    metadata = ConnectorMetadata(
        key="microsoft365",
        name="Microsoft 365",
        category="workspace",
        auth_type="client_credentials",   # org-level, no user OAuth redirect
        scope="org",
        description=(
            "Organization-wide connection. Admins can query any employee's "
            "email using your Microsoft 365 tenant credentials."
        ),
        icon_url="/icons/microsoft365.svg",
        oauth_scopes=[],  # not used for client credentials
        oauth_config={},
    )

    # ------------------------------------------------------------------
    # Client credentials — org-level token (no user interaction)
    # ------------------------------------------------------------------

    async def get_org_token(self) -> dict[str, Any]:
        """
        Obtain an application-level access token via the client credentials flow.
        Returns {"access_token": "...", "expires_at": datetime, "token_type": "Bearer"}.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "scope": _APP_SCOPE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
            return {
                "access_token": data["access_token"],
                "token_type": data.get("token_type", "Bearer"),
                "expires_at": expires_at,
            }

    # ------------------------------------------------------------------
    # BaseConnector interface — OAuth methods not used for this connector
    # ------------------------------------------------------------------

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Microsoft 365 uses org-level client credentials, not user OAuth")

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError("Microsoft 365 uses org-level client credentials, not user OAuth")

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        """Client credentials tokens cannot be refreshed — just get a new one."""
        return await self.get_org_token()

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        """Verify the app token works by listing users (requires User.Read.All)."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/users",
                params={"$top": 1, "$select": "id"},
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return resp.status_code == 200

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        """
        Fetch emails from a specific employee's mailbox.

        The caller (AI service) sets `credentials["target_user"]` to the
        employee's email address (e.g. john@company.com).  If not set,
        we return a helpful message instead of crashing.
        """
        target_user: str | None = credentials.get("target_user")
        if not target_user:
            return {
                "results": [],
                "source": "outlook",
                "message": (
                    "No target employee specified. "
                    "Ask like: 'Show emails for john@company.com' or "
                    "'Show inbox for John Smith'."
                ),
            }

        access_token = credentials["access_token"]
        # Sanitize — basic guard against path injection
        if "/" in target_user or "\\" in target_user:
            return {"results": [], "source": "outlook", "error": "Invalid target user"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/users/{target_user}/messages",
                params={
                    "$search": f'"{query[:100]}"',
                    "$top": 10,
                    "$select": "subject,from,receivedDateTime,bodyPreview",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "ConsistencyLevel": "eventual",
                },
            )
            if resp.status_code == 404:
                return {
                    "results": [],
                    "source": "outlook",
                    "error": f"User '{target_user}' not found in your Microsoft 365 tenant.",
                }
            if resp.status_code == 403:
                return {
                    "results": [],
                    "source": "outlook",
                    "error": (
                        "Permission denied. Ensure your Azure AD app has "
                        "Mail.Read application permission with admin consent granted."
                    ),
                }
            resp.raise_for_status()
            data = resp.json()
            return {
                "results": data.get("value", []),
                "source": "outlook",
                "target_user": target_user,
            }
