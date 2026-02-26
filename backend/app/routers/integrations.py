"""Integration Hub router — connector listing, OAuth flows, and management."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_org_membership, require_org_admin
from app.connectors import registry
from app.connectors.oauth_manager import generate_state, parse_state
from app.database import get_db
from app.models.integration import Connector, Integration, IntegrationCredential
from app.schemas.integration import (
    ConnectorOut,
    IntegrationOut,
    OAuthCallbackRequest,
    OAuthStartResponse,
    OrgConnectRequest,
)
from app.services.encryption import decrypt, encrypt
from app.config import settings

router = APIRouter(prefix="/integrations", tags=["integrations"])

_REDIRECT_URI = f"{settings.FRONTEND_URL}/api/oauth/callback"


# ── Connector catalogue ───────────────────────────────────────────────────────

@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(db: Annotated[AsyncSession, Depends(get_db)]) -> list[ConnectorOut]:
    result = await db.execute(select(Connector).where(Connector.is_available == True))  # noqa: E712
    return [ConnectorOut.model_validate(c) for c in result.scalars().all()]


# ── OAuth flow ────────────────────────────────────────────────────────────────

@router.get("/oauth/start", response_model=OAuthStartResponse)
async def start_oauth(
    connector_key: str,
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OAuthStartResponse:
    await get_current_org_membership(str(org_id), current_user, db)
    connector = registry.get_instance(connector_key)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_key}' not found")

    state = generate_state(str(org_id), connector_key)
    url = await connector.get_oauth_url(state=state, redirect_uri=_REDIRECT_URI)
    return OAuthStartResponse(authorization_url=url, state=state)


@router.post("/oauth/callback", response_model=IntegrationOut)
async def oauth_callback(
    body: OAuthCallbackRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationOut:
    """Receive the OAuth callback code and exchange it for tokens."""
    try:
        org_id, connector_key, _ = parse_state(body.state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if connector_key != body.connector_key:
        raise HTTPException(status_code=400, detail="Connector key mismatch in state")

    await get_current_org_membership(org_id, current_user, db)
    connector = registry.get_instance(connector_key)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_key}' not found")

    tokens = await connector.exchange_code(code=body.code, redirect_uri=_REDIRECT_URI)

    # Upsert Integration record
    existing = await db.execute(
        select(Integration).where(
            Integration.org_id == org_id,
            Integration.connector_key == connector_key,
            Integration.scope == connector.metadata.scope,
        )
    )
    integration = existing.scalar_one_or_none()
    if not integration:
        integration = Integration(
            org_id=uuid.UUID(org_id),
            connector_key=connector_key,
            scope=connector.metadata.scope,
            user_id=current_user.id if connector.metadata.scope == "user" else None,
        )
        db.add(integration)
        await db.flush()

    integration.status = "connected"
    integration.last_synced_at = datetime.now(timezone.utc)

    # Upsert credentials (encrypted)
    cred_result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.integration_id == integration.id)
    )
    cred = cred_result.scalar_one_or_none()
    if not cred:
        cred = IntegrationCredential(integration_id=integration.id)
        db.add(cred)

    cred.access_token = encrypt(tokens["access_token"])
    cred.refresh_token = encrypt(tokens["refresh_token"]) if tokens.get("refresh_token") else None
    cred.token_type = tokens.get("token_type")
    cred.expires_at = tokens.get("expires_at")
    cred.scope = tokens.get("scope")
    # Exclude sensitive and non-JSON-serializable fields from raw_data.
    # expires_at is a datetime (stored separately above); access/refresh tokens are encrypted above.
    _skip = {"access_token", "refresh_token", "expires_at"}
    cred.raw_data = {k: v for k, v in tokens.items() if k not in _skip}

    await db.flush()
    return IntegrationOut.model_validate(integration)


# ── Org-level client-credentials connect ─────────────────────────────────────

@router.post("/org-connect", response_model=IntegrationOut)
async def org_connect(
    body: OrgConnectRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationOut:
    """
    Connect an org-level integration using the client credentials flow.
    No user OAuth redirect required — uses Azure AD app credentials directly.
    Only org admins can perform this action.
    """
    await require_org_admin(str(body.org_id), current_user, db)
    connector = registry.get_instance(body.connector_key)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{body.connector_key}' not found")

    allowed_auth_types = {"client_credentials", "api_key"}
    if connector.metadata.auth_type not in allowed_auth_types:
        raise HTTPException(
            status_code=400,
            detail="This connector uses OAuth. Use the OAuth flow instead.",
        )

    # For client_credentials connectors: fetch an app-level token.
    # For api_key connectors: verify the key is set in env, then store a placeholder.
    if connector.metadata.auth_type == "client_credentials":
        try:
            tokens = await connector.get_org_token()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to obtain org token: {exc}") from exc
        access_token_value = tokens["access_token"]
        token_type_value = tokens.get("token_type", "Bearer")
        expires_at_value = tokens.get("expires_at")
        scope_value = "https://graph.microsoft.com/.default"
        raw_data_value: dict = {"auth_type": "client_credentials"}
    else:
        # api_key — verify connectivity
        ok = await connector.test_connection({})
        if not ok:
            raise HTTPException(
                status_code=502,
                detail="Could not connect using the configured API key. Check RECALL_API_KEY in .env.",
            )
        access_token_value = "api_key"   # sentinel; real key read from env
        token_type_value = "ApiKey"
        expires_at_value = None
        scope_value = "api_key"
        raw_data_value = {"auth_type": "api_key"}

    # Upsert Integration
    existing = await db.execute(
        select(Integration).where(
            Integration.org_id == body.org_id,
            Integration.connector_key == body.connector_key,
            Integration.scope == "org",
        )
    )
    integration = existing.scalar_one_or_none()
    if not integration:
        integration = Integration(
            org_id=body.org_id,
            connector_key=body.connector_key,
            scope="org",
            user_id=None,
        )
        db.add(integration)
        await db.flush()

    integration.status = "connected"
    integration.last_synced_at = datetime.now(timezone.utc)

    # Upsert credentials
    cred_result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.integration_id == integration.id)
    )
    cred = cred_result.scalar_one_or_none()
    if not cred:
        cred = IntegrationCredential(integration_id=integration.id)
        db.add(cred)

    cred.access_token = encrypt(access_token_value)
    cred.refresh_token = None
    cred.token_type = token_type_value
    cred.expires_at = expires_at_value
    cred.scope = scope_value
    cred.raw_data = raw_data_value

    await db.flush()
    return IntegrationOut.model_validate(integration)


# ── Org integrations ──────────────────────────────────────────────────────────

@router.get("/{org_id}", response_model=list[IntegrationOut])
async def list_org_integrations(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IntegrationOut]:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(Integration).where(Integration.org_id == org_id)
    )
    return [IntegrationOut.model_validate(i) for i in result.scalars().all()]


@router.delete("/{org_id}/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_integration(
    org_id: uuid.UUID,
    integration_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.org_id == org_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    integration.status = "disconnected"
    await db.flush()


# ── OneDrive video URL helper ─────────────────────────────────────────────────

@router.get("/onedrive/video-url")
async def get_onedrive_video_url(
    user_email: str,
    item_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """
    Return a short-lived pre-authenticated download URL for an OneDrive video file.
    The client can use this URL directly as a <video src="..."> source.
    Requires the org to have an active OneDrive integration.
    """
    # Verify caller belongs to an org with an active OneDrive integration
    from app.connectors.workspace.onedrive.connector import OneDriveConnector

    connector = OneDriveConnector()
    try:
        token_data = await connector.get_org_token()
        token = token_data["access_token"]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to get org token: {exc}") from exc

    _GRAPH_URL = "https://graph.microsoft.com/v1.0"
    async with httpx.AsyncClient(timeout=15) as client:
        # Do NOT use $select — @microsoft.graph.downloadUrl is only returned
        # when no $select is specified (Graph API behaviour).
        resp = await client.get(
            f"{_GRAPH_URL}/users/{user_email}/drive/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="File not found")
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail="Access denied to this file")
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"Graph API error {resp.status_code}")

    data = resp.json()
    download_url = data.get("@microsoft.graph.downloadUrl")
    if not download_url:
        raise HTTPException(status_code=404, detail="Download URL not available for this file")

    return JSONResponse({"url": download_url, "name": data.get("name", "")})
