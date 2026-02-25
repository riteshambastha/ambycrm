import uuid
from datetime import datetime

from pydantic import BaseModel


class ConnectorOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    category: str
    auth_type: str
    icon_url: str | None
    description: str | None
    is_available: bool

    model_config = {"from_attributes": True}


class IntegrationOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    connector_key: str
    scope: str
    status: str
    display_name: str | None
    external_account_id: str | None
    last_synced_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    connector_key: str
    org_id: str


class OrgConnectRequest(BaseModel):
    """Connect an org-level integration using client credentials (no OAuth redirect)."""
    connector_key: str
    org_id: uuid.UUID
