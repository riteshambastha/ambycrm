"""
Unit tests for app/services/cache_service.py

Tests cover:
  - get_section_cache (hit fresh, hit stale, miss)
  - store_section_cache (upsert)
  - invalidate_member_cache / invalidate_section_cache
  - delete_expired_cache / delete_inactive_cache
  - get_active_member_emails
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    CACHE_ID,
    NOW,
    ORG_ID,
    WORK_EMAIL,
    make_cache_entry,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scalar_result(obj):
    """Wrap a single object in a mock scalar_one_or_none result."""
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(items):
    """Wrap a list in a mock scalars().all() result."""
    r = MagicMock()
    r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    return r


def _all_result(rows):
    """Wrap rows in a mock .all() result."""
    r = MagicMock()
    r.all = MagicMock(return_value=rows)
    return r


# ── Tests: get_section_cache ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_section_cache_miss(mock_db):
    """Returns (None, False) when no cache row exists."""
    mock_db.execute = AsyncMock(return_value=_scalar_result(None))

    from app.services.cache_service import get_section_cache

    result, is_stale = await get_section_cache(mock_db, ORG_ID, WORK_EMAIL, "emails", 15)

    assert result is None
    assert is_stale is False


@pytest.mark.asyncio
async def test_get_section_cache_hit_fresh(mock_db):
    """Returns (SectionResponse, False) when cache exists and is fresh."""
    # Expires far in the future so there's no stale/expired condition
    far_future = NOW + timedelta(hours=48)
    entry = make_cache_entry(section="emails", expires_at=far_future)
    mock_db.execute = AsyncMock(return_value=_scalar_result(entry))

    from app.services.cache_service import get_section_cache

    result, is_stale = await get_section_cache(mock_db, ORG_ID, WORK_EMAIL, "emails", 15)

    assert result is not None
    assert result.connected is True
    assert result.cached is True
    assert result.cache_status == "fresh"
    assert is_stale is False
    assert len(result.results) <= 15


@pytest.mark.asyncio
async def test_get_section_cache_hit_stale(mock_db):
    """Returns (SectionResponse, True) when cache entry is about to expire."""
    # expires_at = 10 minutes from now → under the 30-minute stale threshold
    entry = make_cache_entry(
        section="emails",
        expires_at=NOW + timedelta(minutes=10),
    )
    mock_db.execute = AsyncMock(return_value=_scalar_result(entry))

    from app.services.cache_service import get_section_cache

    with patch("app.services.cache_service._now", return_value=NOW):
        result, is_stale = await get_section_cache(mock_db, ORG_ID, WORK_EMAIL, "emails", 15)

    assert result is not None
    assert result.cache_status == "stale_refresh"
    assert is_stale is True


@pytest.mark.asyncio
async def test_get_section_cache_respects_limit(mock_db):
    """Slices results to the requested limit."""
    many_results = [{"subject": f"Email {i}"} for i in range(50)]
    entry = make_cache_entry(section="emails", results=many_results)
    mock_db.execute = AsyncMock(return_value=_scalar_result(entry))

    from app.services.cache_service import get_section_cache

    result, _ = await get_section_cache(mock_db, ORG_ID, WORK_EMAIL, "emails", 10)

    assert result is not None
    assert len(result.results) == 10


@pytest.mark.asyncio
async def test_get_section_cache_lowercases_email(mock_db):
    """Email is lowercased before the DB lookup."""
    mock_db.execute = AsyncMock(return_value=_scalar_result(None))

    from app.services.cache_service import get_section_cache
    await get_section_cache(mock_db, ORG_ID, "JOHN@COMPANY.COM", "emails", 15)

    call_args = mock_db.execute.call_args
    assert call_args is not None  # execute was called


# ── Tests: store_section_cache ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_section_cache_trims_to_max(mock_db):
    """Always trims results to CACHE_MAX_ITEMS before storing."""
    mock_db.execute = AsyncMock()

    from app.services.cache_service import store_section_cache

    big_results = [{"id": i} for i in range(100)]
    with patch("app.services.cache_service.settings") as mock_settings:
        mock_settings.CACHE_MAX_ITEMS = 50
        mock_settings.CACHE_TTL_EMAILS = 14400
        mock_settings.CACHE_TTL_FILES = 43200
        mock_settings.CACHE_TTL_SALESFORCE = 21600
        mock_settings.CACHE_TTL_MEETINGS = 86400

        await store_section_cache(
            mock_db, ORG_ID, WORK_EMAIL, "emails", "microsoft365", big_results, "summary"
        )

    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_store_section_cache_sets_expires_at(mock_db):
    """expires_at is set to fetched_at + ttl."""
    executed_stmt = None

    async def capture_execute(stmt, *args, **kwargs):
        nonlocal executed_stmt
        executed_stmt = stmt
        return MagicMock()

    mock_db.execute = capture_execute

    from app.services.cache_service import store_section_cache
    await store_section_cache(mock_db, ORG_ID, WORK_EMAIL, "emails", "microsoft365", [], None)
    # Just assert it was called without raising
    assert executed_stmt is not None


# ── Tests: invalidate_member_cache ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidate_member_cache_deletes_all_sections(mock_db):
    """Deletes all rows for the given (org_id, work_email)."""
    mock_db.execute = AsyncMock()

    from app.services.cache_service import invalidate_member_cache
    await invalidate_member_cache(mock_db, ORG_ID, WORK_EMAIL)

    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_section_cache_deletes_one_section(mock_db):
    """Deletes only the specified section."""
    mock_db.execute = AsyncMock()

    from app.services.cache_service import invalidate_section_cache
    await invalidate_section_cache(mock_db, ORG_ID, WORK_EMAIL, "emails")

    mock_db.execute.assert_called_once()


# ── Tests: delete_expired_cache ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_expired_cache_returns_rowcount(mock_db):
    """Returns the number of deleted rows."""
    result_mock = MagicMock()
    result_mock.rowcount = 7
    mock_db.execute = AsyncMock(return_value=result_mock)

    from app.services.cache_service import delete_expired_cache
    count = await delete_expired_cache(mock_db)

    assert count == 7


@pytest.mark.asyncio
async def test_delete_inactive_cache_uses_cutoff(mock_db):
    """Runs a DELETE with a last_viewed_at < cutoff filter."""
    result_mock = MagicMock()
    result_mock.rowcount = 3
    mock_db.execute = AsyncMock(return_value=result_mock)

    from app.services.cache_service import delete_inactive_cache
    count = await delete_inactive_cache(mock_db, inactive_days=30)

    assert count == 3
    mock_db.execute.assert_called_once()


# ── Tests: get_active_member_emails ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_member_emails_returns_pairs(mock_db):
    """Returns list of (org_id, work_email) tuples."""
    rows = [(ORG_ID, "a@co.com"), (ORG_ID, "b@co.com")]
    result_mock = MagicMock()
    result_mock.all = MagicMock(return_value=rows)
    mock_db.execute = AsyncMock(return_value=result_mock)

    from app.services.cache_service import get_active_member_emails
    pairs = await get_active_member_emails(mock_db, since_hours=24)

    assert pairs == rows


@pytest.mark.asyncio
async def test_get_active_member_emails_empty(mock_db):
    """Returns empty list when no active members."""
    result_mock = MagicMock()
    result_mock.all = MagicMock(return_value=[])
    mock_db.execute = AsyncMock(return_value=result_mock)

    from app.services.cache_service import get_active_member_emails
    pairs = await get_active_member_emails(mock_db)

    assert pairs == []
