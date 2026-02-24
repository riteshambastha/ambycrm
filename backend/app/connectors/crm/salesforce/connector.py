"""Salesforce CRM connector."""

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

_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
_AUTH_URL = "https://login.salesforce.com/services/oauth2/authorize"
_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"


class SalesforceConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="salesforce",
        name="Salesforce",
        category="crm",
        auth_type="oauth2",
        scope="org",
        description="Connect your Salesforce CRM to query deals, contacts, and opportunities.",
        icon_url="/icons/salesforce.svg",
        oauth_scopes=["api", "refresh_token", "offline_access"],
        oauth_config={
            "auth_url": _AUTH_URL,
            "token_url": _TOKEN_URL,
        },
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
        instance_url = credentials.get("instance_url", "https://na1.salesforce.com")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{instance_url}/services/data/v59.0/",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        """Query Salesforce SOQL based on the natural-language query."""
        instance_url = credentials.get("instance_url", "https://na1.salesforce.com")
        # Default: search opportunities containing keywords from the query
        keywords = query.replace("'", "\\'")[:100]
        soql = (
            f"SELECT Id, Name, StageName, Amount, CloseDate, Account.Name "
            f"FROM Opportunity WHERE Name LIKE '%{keywords}%' OR Account.Name LIKE '%{keywords}%' "
            f"LIMIT 20"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{instance_url}/services/data/v59.0/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"results": data.get("records", []), "total": data.get("totalSize", 0)}
