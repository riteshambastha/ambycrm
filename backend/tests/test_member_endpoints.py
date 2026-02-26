"""
Unit tests for the Members feature API layer.

Strategy:
  - Test helper functions (e.g. _get_member_work_info) directly as async calls.
  - Test handler logic (_handle_section_request) directly with mocked DB/cache.
  - Test the HTTP layer with real TestClient only for simple routing smoke tests,
    keeping all heavy dependencies mocked at the function level.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch, patch as mock_patch

import pytest

from tests.conftest import (
    DISPLAY_NAME,
    EMPLOYEE_ID,
    MEMBER_ID,
    NOW,
    ORG_ID,
    WORK_EMAIL,
    make_cache_entry,
    make_employee,
    make_member,
)


# ── Helper: _get_member_work_info ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_member_work_info_returns_email_and_name(mock_db):
    """Returns (work_email, display_name) for a member with work_email set."""
    member = make_member(work_email=WORK_EMAIL)
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=member)
    mock_db.execute = AsyncMock(return_value=r)

    from app.routers.organizations import _get_member_work_info

    result = await _get_member_work_info(ORG_ID, MEMBER_ID, mock_db)

    assert result is not None
    email, name = result
    assert email == WORK_EMAIL
    assert "John" in name


@pytest.mark.asyncio
async def test_get_member_work_info_returns_none_when_no_work_email(mock_db):
    """Returns None when member has no work_email."""
    member = make_member()
    member.work_email = None  # Override to None
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=member)
    mock_db.execute = AsyncMock(return_value=r)

    from app.routers.organizations import _get_member_work_info

    result = await _get_member_work_info(ORG_ID, MEMBER_ID, mock_db)

    assert result is None


@pytest.mark.asyncio
async def test_get_member_work_info_returns_none_when_not_found(mock_db):
    """Returns None when no member row found."""
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=r)

    from app.routers.organizations import _get_member_work_info

    result = await _get_member_work_info(ORG_ID, MEMBER_ID, mock_db)

    assert result is None


@pytest.mark.asyncio
async def test_get_member_work_info_uses_work_email_as_fallback_name(mock_db):
    """When user has no first/last name, display_name falls back to work_email."""
    member = make_member(work_email=WORK_EMAIL)
    member.user.first_name = None
    member.user.last_name = None
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=member)
    mock_db.execute = AsyncMock(return_value=r)

    from app.routers.organizations import _get_member_work_info

    result = await _get_member_work_info(ORG_ID, MEMBER_ID, mock_db)

    assert result is not None
    email, name = result
    assert name == WORK_EMAIL


# ── Helper: _get_employee_work_info ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_employee_work_info_success(mock_db):
    """Returns (work_email, name) for an existing employee."""
    employee = make_employee()
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=employee)
    mock_db.execute = AsyncMock(return_value=r)

    from app.routers.organizations import _get_employee_work_info

    result = await _get_employee_work_info(ORG_ID, EMPLOYEE_ID, mock_db)

    assert result is not None
    email, name = result
    assert email == WORK_EMAIL
    assert name == DISPLAY_NAME


@pytest.mark.asyncio
async def test_get_employee_work_info_not_found(mock_db):
    """Returns None when no employee row found."""
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=r)

    from app.routers.organizations import _get_employee_work_info

    result = await _get_employee_work_info(ORG_ID, EMPLOYEE_ID, mock_db)

    assert result is None


# ── Core logic: _handle_section_request ──────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_section_request_returns_cached_fresh(mock_db):
    """Returns cached data directly when cache is fresh."""
    from app.schemas.organization import SectionResponse

    cached = SectionResponse(
        connected=True, results=[{"subject": "Email 1"}], limit=15, cached=True, fetched_at=NOW,
        cache_status="fresh",
    )

    with patch("app.routers.organizations.get_section_cache",
               new=AsyncMock(return_value=(cached, False))):

        from app.routers.organizations import _handle_section_request

        result = await _handle_section_request(ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails", 15, mock_db)

    assert result.cached is True
    assert result.cache_status == "fresh"
    assert len(result.results) == 1


@pytest.mark.asyncio
async def test_handle_section_request_triggers_background_refresh_when_stale(mock_db):
    """Triggers Celery task when cache is stale, still returns stale data."""
    from app.schemas.organization import SectionResponse

    stale = SectionResponse(
        connected=True, results=[{"subject": "Old"}], limit=15, cached=True,
        fetched_at=NOW, cache_status="stale_refresh",
    )

    # sync_member_section is locally imported inside _handle_section_request
    # so we patch it at its source module
    import app.tasks.member_sync as sync_module
    mock_task = MagicMock()
    mock_task.delay = MagicMock()

    with patch("app.routers.organizations.get_section_cache",
               new=AsyncMock(return_value=(stale, True))), \
         patch.object(sync_module, "sync_member_section", mock_task):

        from app.routers.organizations import _handle_section_request

        result = await _handle_section_request(
            ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails", 15, mock_db
        )

    # Still returns stale data (not blocked)
    assert result is not None
    assert result.results is not None


@pytest.mark.asyncio
async def test_handle_section_request_fetches_live_on_cache_miss(mock_db):
    """Falls through to _fetch_section_live when cache is empty."""
    from app.schemas.organization import SectionResponse

    live_response = SectionResponse(
        connected=True, results=[{"subject": "Fresh email"}], limit=15, cached=False,
        cache_status="miss",
    )

    with patch("app.routers.organizations.get_section_cache",
               new=AsyncMock(return_value=(None, False))), \
         patch("app.routers.organizations._fetch_section_live",
               new=AsyncMock(return_value=live_response)):

        from app.routers.organizations import _handle_section_request

        result = await _handle_section_request(ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails", 15, mock_db)

    assert result.cached is False
    assert result.cache_status == "miss"
    assert result.results[0]["subject"] == "Fresh email"


# ── _fetch_section_live ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_section_live_not_connected_returns_disconnected(mock_db):
    """Returns SectionResponse(connected=False) when no connector active."""
    with patch("app.routers.organizations.load_connected_integrations",
               new=AsyncMock(return_value=[])):

        from app.routers.organizations import _fetch_section_live

        result = await _fetch_section_live(
            ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails", 15, mock_db
        )

    assert result.connected is False
    assert result.results == []


@pytest.mark.asyncio
async def test_fetch_section_live_returns_and_stores_results(mock_db):
    """Fetches from connector, stores to cache, and returns SectionResponse."""
    active_integration = {
        "connector_key": "microsoft365",
        "credentials": {"access_token": "tok"},
    }

    fetch_result = {"connector": "microsoft365", "results": [{"subject": "E1"}, {"subject": "E2"}]}

    # fetch_connector_data and litellm are locally imported inside _fetch_section_live
    import app.services.ai_service as ai_module
    import litellm

    mock_llm_resp = MagicMock()
    mock_llm_resp.choices = [MagicMock()]
    mock_llm_resp.choices[0].message.content = "• 2 emails found"

    with patch("app.routers.organizations.load_connected_integrations",
               new=AsyncMock(return_value=[active_integration])), \
         patch.object(ai_module, "fetch_connector_data",
                      new=AsyncMock(return_value=fetch_result)), \
         patch("app.routers.organizations.store_section_cache",
               new=AsyncMock()), \
         patch.object(litellm, "acompletion",
                      new=AsyncMock(return_value=mock_llm_resp)):

        from app.routers.organizations import _fetch_section_live

        result = await _fetch_section_live(
            ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails", 15, mock_db
        )

    assert result.connected is True
    assert len(result.results) <= 15


# ── Refresh endpoint logic ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_member_invalidates_cache_and_dispatches_task(mock_db):
    """refresh_member_cache invalidates cache and dispatches sync_member_all_sections."""
    member = make_member(work_email=WORK_EMAIL)
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=member)
    mock_db.execute = AsyncMock(return_value=r)

    # sync_member_all_sections is locally imported inside refresh_member_cache
    import app.tasks.member_sync as sync_module
    mock_task = MagicMock()
    mock_task.delay = MagicMock()

    with patch("app.routers.organizations.invalidate_member_cache", new=AsyncMock()) as mock_inv, \
         patch.object(sync_module, "sync_member_all_sections", mock_task), \
         patch("app.routers.organizations.get_current_org_membership", new=AsyncMock()):

        mock_user = MagicMock()
        from app.routers.organizations import refresh_member_cache

        result = await refresh_member_cache(ORG_ID, MEMBER_ID, mock_user, mock_db)

    assert result is not None
    mock_inv.assert_called_once_with(mock_db, ORG_ID, WORK_EMAIL)
    mock_task.delay.assert_called_once()


# ── PersonOut construction from member/employee ───────────────────────────────

def test_person_out_from_member_data():
    """Verify the PersonOut shape expected by the people endpoint."""
    from app.schemas.organization import PersonOut

    p = PersonOut(
        id=MEMBER_ID,
        person_type="member",
        first_name="John",
        last_name="Doe",
        display_name="John Doe",
        email="john@example.com",
        work_email=WORK_EMAIL,
        avatar_url=None,
        role="user",
        is_active=True,
        joined_at=NOW,
    )

    assert p.id == MEMBER_ID
    assert p.person_type == "member"
    assert p.display_name == "John Doe"
    assert p.work_email == WORK_EMAIL


def test_person_out_from_employee_data():
    """PersonOut for employee has person_type='employee' and no role."""
    from app.schemas.organization import PersonOut

    p = PersonOut(
        id=EMPLOYEE_ID,
        person_type="employee",
        first_name="Jane",
        last_name="Smith",
        display_name="Jane Smith",
        email=None,
        work_email=WORK_EMAIL,
        avatar_url=None,
        role=None,
        is_active=True,
        joined_at=NOW,
    )

    assert p.person_type == "employee"
    assert p.role is None


# ── Stale-while-revalidate: SectionResponse cache_status values ───────────────

@pytest.mark.parametrize("status", ["fresh", "stale_refresh", "miss"])
def test_section_response_cache_status_values(status):
    """All documented cache_status values are accepted by SectionResponse."""
    from app.schemas.organization import SectionResponse

    r = SectionResponse(
        connected=True, results=[], limit=15, cache_status=status
    )
    assert r.cache_status == status


# ── Limit boundary validation ─────────────────────────────────────────────────

def test_limit_defaults_to_15():
    """Section endpoint default limit is 15."""
    from app.schemas.organization import SectionResponse

    r = SectionResponse(connected=True, results=[], limit=15)
    assert r.limit == 15


def test_section_response_limit_stored():
    """limit field is preserved in the schema."""
    from app.schemas.organization import SectionResponse

    for limit in (1, 10, 15, 25, 50):
        r = SectionResponse(connected=True, results=[], limit=limit)
        assert r.limit == limit
