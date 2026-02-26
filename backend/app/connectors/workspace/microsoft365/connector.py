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
        """Verify the app credentials work by fetching a fresh token and listing users."""
        try:
            fresh = await self.get_org_token()
            access_token = fresh["access_token"]
        except Exception:
            return False
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/users",
                params={"$top": 1, "$select": "id"},
                headers={"Authorization": f"Bearer {access_token}"},
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

        Always fetches a fresh app-level token (client credentials tokens
        expire in ~1 hour; we never want to use a stale stored token).
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

        # Always get a fresh token — client credentials tokens expire in ~1h
        try:
            fresh = await self.get_org_token()
            access_token = fresh["access_token"]
        except Exception as exc:
            return {"results": [], "source": "outlook", "error": f"Failed to get org token: {exc}"}

        # Sanitize — basic guard against path injection
        if "/" in target_user or "\\" in target_user:
            return {"results": [], "source": "outlook", "error": "Invalid target user"}

        # Extract a meaningful keyword from the query (strip navigation words)
        # so we can pass a subject-level search term rather than the full prompt.
        _skip_words = {
            "show", "get", "find", "fetch", "display", "list", "inbox", "emails",
            "email", "for", "of", "me", "the", "my", "from", "recent", "latest",
            "messages", "mail", "about", "outlook", "microsoft",
            # common English stop words that are not email subject keywords
            "can", "you", "see", "please", "could", "would", "should", "will",
            "some", "any", "data", "info", "information", "details", "check",
            "that", "this", "there", "their", "they", "has", "have", "are",
            "not", "but", "and", "its", "our", "your", "with", "into", "read",
        }
        keyword_parts = [
            w for w in query.lower().split()
            if w not in _skip_words and "@" not in w and len(w) > 3
        ]
        keyword = " ".join(keyword_parts[:4]).strip()  # up to 4 meaningful words

        # Detect if user wants more emails (e.g. "last 50 emails", "all emails")
        _lower_query = query.lower()
        top = 25  # sensible default
        for token in _lower_query.split():
            if token.isdigit():
                top = min(int(token), 50)  # cap at 50
                break
        if any(w in _lower_query for w in ("all", "every", "everything")):
            top = 50

        # Build params — use $search only when there is a meaningful keyword
        params: dict[str, Any] = {
            "$top": top,
            "$select": "subject,from,toRecipients,receivedDateTime,bodyPreview,body",
            "$orderby": "receivedDateTime desc",
        }
        headers: dict[str, str] = {
            "Authorization": f"Bearer {access_token}",
            # Ask Graph to return body as plain text (avoids huge HTML blobs)
            "Prefer": 'outlook.body-content-type="text"',
        }
        if keyword:
            params["$search"] = f'"{keyword}"'
            headers["ConsistencyLevel"] = "eventual"
            # $search and $orderby can't be combined
            del params["$orderby"]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/users/{target_user}/messages",
                params=params,
                headers=headers,
            )
            if resp.status_code == 401:
                return {
                    "results": [],
                    "source": "outlook",
                    "error": "Authentication failed — the org token is invalid.",
                }
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
            # Flatten each email into a clean dict the LLM can read easily
            emails = []
            for msg in data.get("value", []):
                body_text = (msg.get("body") or {}).get("content", "")
                # Truncate very long bodies
                if len(body_text) > 2000:
                    body_text = body_text[:2000] + "… [truncated]"
                emails.append({
                    "subject": msg.get("subject"),
                    "from": (msg.get("from") or {}).get("emailAddress", {}).get("address"),
                    "from_name": (msg.get("from") or {}).get("emailAddress", {}).get("name"),
                    "to": [
                        r.get("emailAddress", {}).get("address")
                        for r in (msg.get("toRecipients") or [])
                    ],
                    "received": msg.get("receivedDateTime"),
                    "body": body_text or msg.get("bodyPreview", ""),
                })
            return {
                "results": emails,
                "source": "outlook",
                "target_user": target_user,
                "searched_for": keyword or "(latest emails)",
            }
