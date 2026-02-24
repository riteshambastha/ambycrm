"""Celery background tasks for OAuth token refresh and data sync."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "ambycrm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-expired-tokens": {
            "task": "app.tasks.sync_tasks.refresh_expired_tokens",
            "schedule": 300,  # every 5 minutes
        },
    },
)


@celery_app.task(name="app.tasks.sync_tasks.refresh_expired_tokens", bind=True, max_retries=3)
def refresh_expired_tokens(self) -> dict:
    """
    Find all integrations with credentials expiring in the next 10 minutes
    and refresh their access tokens.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.integration import Integration, IntegrationCredential
    from app.connectors.registry import ConnectorRegistry
    from app.services.encryption import decrypt, encrypt

    engine = create_engine(settings.DATABASE_URL_SYNC)
    reg = ConnectorRegistry()
    reg.discover()

    refreshed = 0
    errors = 0

    with Session(engine) as session:
        soon = datetime.now(timezone.utc) + timedelta(minutes=10)
        result = session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.expires_at <= soon,
                IntegrationCredential.refresh_token != None,  # noqa: E711
            )
        )
        creds = result.scalars().all()

        for cred in creds:
            integration = session.get(Integration, cred.integration_id)
            if not integration or integration.status != "connected":
                continue
            connector = reg.get_instance(integration.connector_key)
            if not connector:
                continue
            try:
                import asyncio
                credentials = {
                    "access_token": decrypt(cred.access_token),
                    "refresh_token": decrypt(cred.refresh_token),
                }
                new_tokens = asyncio.run(connector.refresh_token(credentials))
                cred.access_token = encrypt(new_tokens["access_token"])
                if new_tokens.get("refresh_token"):
                    cred.refresh_token = encrypt(new_tokens["refresh_token"])
                cred.expires_at = new_tokens.get("expires_at")
                session.commit()
                refreshed += 1
            except Exception:
                errors += 1
                continue

    return {"refreshed": refreshed, "errors": errors}
