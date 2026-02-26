"""
Shared test fixtures for the Members feature test suite.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Common UUIDs ─────────────────────────────────────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
MEMBER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
EMPLOYEE_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
USER_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000004")
CACHE_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000005")

WORK_EMAIL = "john.doe@company.com"
DISPLAY_NAME = "John Doe"

NOW = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)


# ── Async DB session mock ─────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Return a mock async SQLAlchemy session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    return session


# ── Minimal ORM object factories ─────────────────────────────────────────────

def make_cache_entry(
    section: str = "emails",
    results: list | None = None,
    summary: str | None = "Test summary.",
    expires_at: datetime | None = None,
    last_viewed_at: datetime | None = None,
) -> MagicMock:
    from datetime import timedelta

    entry = MagicMock()
    entry.id = CACHE_ID
    entry.org_id = ORG_ID
    entry.work_email = WORK_EMAIL
    entry.section = section
    entry.connector_key = "microsoft365"
    entry.results = results or [{"subject": "Test email", "from": "sender@x.com"}]
    entry.summary = summary
    entry.item_count = len(entry.results)
    entry.fetched_at = NOW
    entry.expires_at = expires_at or (NOW + timedelta(hours=4))
    entry.last_viewed_at = last_viewed_at or NOW
    return entry


def make_member(
    work_email: str = WORK_EMAIL,
    first_name: str = "John",
    last_name: str = "Doe",
) -> MagicMock:
    m = MagicMock()
    m.id = MEMBER_ID
    m.org_id = ORG_ID
    m.user_id = USER_ID
    m.work_email = work_email
    m.role = "user"
    m.is_active = True
    m.joined_at = NOW
    m.user = MagicMock()
    m.user.first_name = first_name
    m.user.last_name = last_name
    m.user.email = "john@example.com"
    m.user.avatar_url = None
    return m


def make_employee(
    work_email: str = WORK_EMAIL,
    name: str = DISPLAY_NAME,
) -> MagicMock:
    e = MagicMock()
    e.id = EMPLOYEE_ID
    e.org_id = ORG_ID
    e.name = name
    e.work_email = work_email
    e.created_at = NOW
    return e


def make_integration(connector_key: str = "microsoft365") -> MagicMock:
    cred = MagicMock()
    cred.access_token = "encrypted_token"
    cred.refresh_token = None
    cred.raw_data = {}

    integration = MagicMock()
    integration.connector_key = connector_key
    integration.status = "connected"
    integration.credentials = [cred]
    return integration
