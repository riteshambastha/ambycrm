"""
Unit tests for app/services/integration_service.py

Tests cover:
  - load_connected_integrations (success, skips missing credentials, skips decrypt errors)
  - is_connector_connected
  - SECTION_CONNECTOR_KEYS mapping completeness
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import ORG_ID, make_integration


def _scalars_result(items):
    r = MagicMock()
    r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    return r


# ── Tests: load_connected_integrations ───────────────────────────────────────

@pytest.mark.asyncio
async def test_load_connected_integrations_returns_decrypted(mock_db):
    """Happy path: connected integration returns decrypted credentials."""
    integration = make_integration("microsoft365")
    mock_db.execute = AsyncMock(return_value=_scalars_result([integration]))

    with patch("app.services.integration_service.decrypt", return_value="plain_token"):
        from app.services.integration_service import load_connected_integrations
        result = await load_connected_integrations(ORG_ID, mock_db)

    assert len(result) == 1
    assert result[0]["connector_key"] == "microsoft365"
    assert result[0]["credentials"]["access_token"] == "plain_token"


@pytest.mark.asyncio
async def test_load_connected_integrations_skips_no_credentials(mock_db):
    """Integration with no credentials is skipped."""
    integration = make_integration("microsoft365")
    integration.credentials = []  # No credentials
    mock_db.execute = AsyncMock(return_value=_scalars_result([integration]))

    from app.services.integration_service import load_connected_integrations
    result = await load_connected_integrations(ORG_ID, mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_load_connected_integrations_skips_decrypt_error(mock_db):
    """Integration where decrypt fails is silently skipped."""
    integration = make_integration("microsoft365")
    mock_db.execute = AsyncMock(return_value=_scalars_result([integration]))

    with patch("app.services.integration_service.decrypt", side_effect=Exception("bad key")):
        from app.services.integration_service import load_connected_integrations
        result = await load_connected_integrations(ORG_ID, mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_load_connected_integrations_multiple_connectors(mock_db):
    """Multiple integrations are all returned."""
    integrations = [
        make_integration("microsoft365"),
        make_integration("onedrive"),
        make_integration("salesforce"),
    ]
    mock_db.execute = AsyncMock(return_value=_scalars_result(integrations))

    with patch("app.services.integration_service.decrypt", return_value="tok"):
        from app.services.integration_service import load_connected_integrations
        result = await load_connected_integrations(ORG_ID, mock_db)

    assert len(result) == 3
    keys = {r["connector_key"] for r in result}
    assert keys == {"microsoft365", "onedrive", "salesforce"}


@pytest.mark.asyncio
async def test_load_connected_integrations_empty(mock_db):
    """No connected integrations returns empty list."""
    mock_db.execute = AsyncMock(return_value=_scalars_result([]))

    from app.services.integration_service import load_connected_integrations
    result = await load_connected_integrations(ORG_ID, mock_db)

    assert result == []


# ── Tests: is_connector_connected ────────────────────────────────────────────

def test_is_connector_connected_true():
    from app.services.integration_service import is_connector_connected

    connected = [{"connector_key": "microsoft365"}, {"connector_key": "onedrive"}]
    assert is_connector_connected(connected, ["microsoft365", "google_workspace"]) is True


def test_is_connector_connected_false():
    from app.services.integration_service import is_connector_connected

    connected = [{"connector_key": "salesforce"}]
    assert is_connector_connected(connected, ["microsoft365", "google_workspace"]) is False


def test_is_connector_connected_empty_connected_list():
    from app.services.integration_service import is_connector_connected

    assert is_connector_connected([], ["microsoft365"]) is False


def test_is_connector_connected_empty_keys():
    from app.services.integration_service import is_connector_connected

    connected = [{"connector_key": "microsoft365"}]
    assert is_connector_connected(connected, []) is False


# ── Tests: SECTION_CONNECTOR_KEYS completeness ────────────────────────────────

def test_section_connector_keys_has_all_four_sections():
    from app.services.integration_service import SECTION_CONNECTOR_KEYS

    assert set(SECTION_CONNECTOR_KEYS.keys()) == {"emails", "files", "salesforce", "meetings"}


def test_section_connector_keys_emails_includes_microsoft365():
    from app.services.integration_service import SECTION_CONNECTOR_KEYS

    assert "microsoft365" in SECTION_CONNECTOR_KEYS["emails"]


def test_section_connector_keys_meetings_includes_teams_and_recall():
    from app.services.integration_service import SECTION_CONNECTOR_KEYS

    assert "teams" in SECTION_CONNECTOR_KEYS["meetings"]
    assert "recall" in SECTION_CONNECTOR_KEYS["meetings"]


def test_section_connector_keys_salesforce_includes_crms():
    from app.services.integration_service import SECTION_CONNECTOR_KEYS

    assert "salesforce" in SECTION_CONNECTOR_KEYS["salesforce"]
    assert "hubspot" in SECTION_CONNECTOR_KEYS["salesforce"]
