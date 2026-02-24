"""HubSpot CRM connector."""

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

_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET", "")
_AUTH_URL = "https://app.hubspot.com/oauth/authorize"
_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"


class HubSpotConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="hubspot",
        name="HubSpot",
        category="crm",
        auth_type="oauth2",
        scope="org",
        description="Connect HubSpot to access contacts, deals, and companies.",
        icon_url="/icons/hubspot.svg",
        oauth_scopes=["crm.objects.deals.read", "crm.objects.contacts.read", "crm.objects.companies.read"],
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
                "https://api.hubapi.com/crm/v3/objects/deals?limit=1",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.hubapi.com/crm/v3/objects/deals/search",
                headers={
                    "Authorization": f"Bearer {credentials['access_token']}",
                    "Content-Type": "application/json",
                },
                json={
                    "filterGroups": [],
                    "properties": ["dealname", "dealstage", "amount", "closedate", "hs_object_id"],
                    "limit": 20,
                    "query": query[:100],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"results": data.get("results", []), "total": data.get("total", 0)}
