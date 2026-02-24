"""SugarCRM connector (OAuth2 password grant)."""

import os
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata
from app.connectors.oauth_manager import compute_expires_at

_BASE_URL = os.getenv("SUGARCRM_BASE_URL", "https://yourinstance.sugarondemand.com")
_CLIENT_ID = os.getenv("SUGARCRM_CLIENT_ID", "sugar")
_CLIENT_SECRET = os.getenv("SUGARCRM_CLIENT_SECRET", "")


class SugarCRMConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="sugarcrm",
        name="SugarCRM",
        category="crm",
        auth_type="api_key",
        scope="org",
        description="Connect SugarCRM to query accounts, leads, and opportunities.",
        icon_url="/icons/sugarcrm.svg",
        oauth_scopes=[],
        oauth_config={},
    )

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        # SugarCRM uses password grant — no redirect URL
        return f"{redirect_uri}?state={state}&connector=sugarcrm"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        # code carries username:password encoded for password grant
        username, password = code.split(":", 1)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE_URL}/rest/v11_1/oauth2/token",
                json={
                    "grant_type": "password",
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "username": username,
                    "password": password,
                    "platform": "base",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            data["expires_at"] = compute_expires_at(data.get("expires_in"))
            return data

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE_URL}/rest/v11_1/oauth2/token",
                json={
                    "grant_type": "refresh_token",
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "refresh_token": credentials["refresh_token"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            data["expires_at"] = compute_expires_at(data.get("expires_in"))
            return data

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_BASE_URL}/rest/v11_1/me",
                headers={"OAuth-Token": credentials["access_token"]},
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_BASE_URL}/rest/v11_1/Opportunities",
                params={"search_term": query[:100], "max_num": 20},
                headers={"OAuth-Token": credentials["access_token"]},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"results": data.get("records", []), "total": data.get("total_count", 0)}
