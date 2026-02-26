"""
Shared integration loading helper.
Extracted from chat.py so it can be reused by section endpoints and Celery tasks.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.integration import Integration, IntegrationCredential
from app.services.encryption import decrypt


async def load_connected_integrations(
    org_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """
    Load all connected integrations for an org with decrypted credentials.
    Returns a list of dicts: [{connector_key, credentials}].
    """
    result = await db.execute(
        select(Integration)
        .options(selectinload(Integration.credentials))
        .where(Integration.org_id == org_id, Integration.status == "connected")
    )
    integrations = result.scalars().all()
    out: list[dict[str, Any]] = []
    for integration in integrations:
        if not integration.credentials:
            continue
        cred: IntegrationCredential = integration.credentials[0]
        try:
            out.append({
                "connector_key": integration.connector_key,
                "credentials": {
                    "access_token": decrypt(cred.access_token),
                    "refresh_token": decrypt(cred.refresh_token) if cred.refresh_token else None,
                    **cred.raw_data,
                },
            })
        except Exception:
            continue
    return out


def is_connector_connected(
    connected_integrations: list[dict[str, Any]],
    connector_keys: list[str],
) -> bool:
    """Return True if at least one of the given connector keys is connected."""
    keys = {i["connector_key"] for i in connected_integrations}
    return bool(keys.intersection(connector_keys))


# Which connector keys serve each section
SECTION_CONNECTOR_KEYS: dict[str, list[str]] = {
    "emails": ["microsoft365", "google_workspace"],
    "files": ["onedrive", "google_workspace"],
    "salesforce": ["salesforce", "hubspot", "dynamics", "sugarcrm"],
    "meetings": ["teams", "recall", "fireflies", "otter"],
}
