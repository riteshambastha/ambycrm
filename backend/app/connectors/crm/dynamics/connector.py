"""Microsoft Dynamics 365 CRM connector."""

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

_CLIENT_ID = os.getenv("DYNAMICS_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("DYNAMICS_CLIENT_SECRET", "")
_TENANT_ID = os.getenv("DYNAMICS_TENANT_ID", "common")
_DYNAMICS_URL = os.getenv("DYNAMICS_ORG_URL", "https://org.crm.dynamics.com")

_AUTH_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/authorize"
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token"


class DynamicsConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="dynamics",
        name="Microsoft Dynamics 365",
        category="crm",
        auth_type="oauth2",
        scope="org",
        description="Connect Microsoft Dynamics 365 to access accounts, contacts, and opportunities.",
        icon_url="/icons/dynamics.svg",
        oauth_scopes=[f"{_DYNAMICS_URL}/.default", "offline_access"],
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
                f"{_DYNAMICS_URL}/api/data/v9.2/accounts?$top=1",
                headers={
                    "Authorization": f"Bearer {credentials['access_token']}",
                    "OData-MaxVersion": "4.0",
                    "OData-Version": "4.0",
                },
            )
            return resp.status_code == 200

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        filter_str = f"contains(name,'{query[:50]}')"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_DYNAMICS_URL}/api/data/v9.2/opportunities",
                params={
                    "$select": "name,statecode,estimatedvalue,estimatedclosedate",
                    "$filter": filter_str,
                    "$top": "20",
                },
                headers={
                    "Authorization": f"Bearer {credentials['access_token']}",
                    "OData-MaxVersion": "4.0",
                    "OData-Version": "4.0",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"results": data.get("value", []), "total": len(data.get("value", []))}
