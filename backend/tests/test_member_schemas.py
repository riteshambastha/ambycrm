"""
Unit tests for the new Pydantic schemas in app/schemas/organization.py

Tests cover:
  - SectionResponse validation, defaults, and field types
  - PersonOut validation and display_name logic
"""

import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import NOW, ORG_ID


# ── SectionResponse tests ────────────────────────────────────────────────────

def test_section_response_minimal():
    """Minimal required fields produce a valid object."""
    from app.schemas.organization import SectionResponse

    r = SectionResponse(connected=True, results=[], limit=15)
    assert r.connected is True
    assert r.results == []
    assert r.limit == 15
    assert r.summary is None
    assert r.error is None
    assert r.cached is False
    assert r.cache_status == "fresh"


def test_section_response_with_results():
    from app.schemas.organization import SectionResponse

    items = [{"subject": "Hello"}, {"subject": "World"}]
    r = SectionResponse(connected=True, results=items, limit=15)
    assert len(r.results) == 2
    assert r.results[0]["subject"] == "Hello"


def test_section_response_not_connected():
    from app.schemas.organization import SectionResponse

    r = SectionResponse(
        connected=False,
        results=[],
        limit=15,
        error="No work email set.",
        cache_status="miss",
    )
    assert r.connected is False
    assert r.error == "No work email set."
    assert r.cache_status == "miss"


def test_section_response_stale_refresh():
    from app.schemas.organization import SectionResponse

    r = SectionResponse(
        connected=True,
        results=[{"x": 1}],
        limit=10,
        cached=True,
        fetched_at=NOW,
        cache_status="stale_refresh",
    )
    assert r.cached is True
    assert r.cache_status == "stale_refresh"
    assert r.fetched_at == NOW


def test_section_response_with_summary():
    from app.schemas.organization import SectionResponse

    r = SectionResponse(
        connected=True,
        results=[],
        limit=15,
        summary="• 3 urgent emails\n• 2 pending replies",
    )
    assert r.summary is not None
    assert "urgent" in r.summary


# ── PersonOut tests ───────────────────────────────────────────────────────────

def test_person_out_member():
    """Member with all fields populated."""
    from app.schemas.organization import PersonOut

    p = PersonOut(
        id=uuid.uuid4(),
        person_type="member",
        first_name="Jane",
        last_name="Smith",
        display_name="Jane Smith",
        email="jane@example.com",
        work_email="jane@company.com",
        avatar_url="https://example.com/avatar.jpg",
        role="org_admin",
        is_active=True,
        joined_at=NOW,
    )
    assert p.person_type == "member"
    assert p.display_name == "Jane Smith"
    assert p.role == "org_admin"
    assert p.is_active is True


def test_person_out_employee_minimal():
    """Employee with minimal fields (no email, no avatar, no role)."""
    from app.schemas.organization import PersonOut

    p = PersonOut(
        id=uuid.uuid4(),
        person_type="employee",
        first_name="Bob",
        last_name=None,
        display_name="Bob",
        email=None,
        work_email="bob@company.com",
        avatar_url=None,
        role=None,
        is_active=True,
        joined_at=NOW,
    )
    assert p.person_type == "employee"
    assert p.email is None
    assert p.role is None
    assert p.avatar_url is None
    assert p.work_email == "bob@company.com"


def test_person_out_inactive():
    from app.schemas.organization import PersonOut

    p = PersonOut(
        id=uuid.uuid4(),
        person_type="member",
        first_name="Old",
        last_name="User",
        display_name="Old User",
        email="old@example.com",
        work_email=None,
        avatar_url=None,
        role="user",
        is_active=False,
        joined_at=None,
    )
    assert p.is_active is False
    assert p.work_email is None
    assert p.joined_at is None


def test_person_out_no_work_email():
    from app.schemas.organization import PersonOut

    p = PersonOut(
        id=uuid.uuid4(),
        person_type="member",
        first_name="No",
        last_name="Email",
        display_name="No Email",
        email="noemail@example.com",
        work_email=None,
        avatar_url=None,
        role="user",
        is_active=True,
        joined_at=NOW,
    )
    assert p.work_email is None
