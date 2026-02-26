"""
Unit tests for app/tasks/member_sync.py

Since Celery tasks use asyncio.run() internally, we test the underlying
async helpers directly, mocking all external dependencies (DB, connectors, LiteLLM).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import DISPLAY_NAME, ORG_ID, WORK_EMAIL, make_cache_entry


# ── Test _generate_summary ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_summary_success():
    """Returns AI text from litellm when results are provided."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "• Urgent item 1\n• Follow up on deal"

    with patch("app.tasks.member_sync.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        from app.tasks.member_sync import _generate_summary

        result = await _generate_summary("emails", [{"subject": "Hello"}])

    assert result == "• Urgent item 1\n• Follow up on deal"


@pytest.mark.asyncio
async def test_generate_summary_empty_results():
    """Returns None immediately when results list is empty."""
    from app.tasks.member_sync import _generate_summary

    result = await _generate_summary("emails", [])
    assert result is None


@pytest.mark.asyncio
async def test_generate_summary_llm_error_returns_none():
    """Returns None (not raises) when litellm throws."""
    with patch("app.tasks.member_sync.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(side_effect=Exception("LLM down"))

        from app.tasks.member_sync import _generate_summary

        result = await _generate_summary("emails", [{"subject": "Hi"}])

    assert result is None


@pytest.mark.asyncio
async def test_generate_summary_all_sections():
    """All 4 section names are handled without KeyError."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "summary"

    with patch("app.tasks.member_sync.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        from app.tasks.member_sync import _generate_summary

        for section in ("emails", "files", "salesforce", "meetings"):
            result = await _generate_summary(section, [{"key": "val"}])
            assert result == "summary"


# ── Test _sync_section_async ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_section_async_skips_when_not_connected(mock_db):
    """Does nothing if no connector for the section is active."""
    mock_db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    ))

    with patch("app.tasks.member_sync.AsyncSessionLocal") as mock_session_cls:
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.member_sync.load_connected_integrations", new=AsyncMock(return_value=[])):
            from app.tasks.member_sync import _sync_section_async

            # Should return without error and without calling store
            await _sync_section_async(ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails")


@pytest.mark.asyncio
async def test_sync_section_async_stores_on_success():
    """Fetches connector data and stores to cache when connector is active."""
    mock_integration = {
        "connector_key": "microsoft365",
        "credentials": {"access_token": "tok"},
    }

    mock_fetch_result = {
        "connector": "microsoft365",
        "results": [{"subject": "Email 1"}],
    }

    mock_summary = "• 1 urgent email"
    mock_db_inner = AsyncMock()
    mock_db_inner.commit = AsyncMock()

    with patch("app.tasks.member_sync.AsyncSessionLocal") as mock_session_cls, \
         patch("app.tasks.member_sync.load_connected_integrations",
               new=AsyncMock(return_value=[mock_integration])), \
         patch("app.tasks.member_sync._generate_summary",
               new=AsyncMock(return_value=mock_summary)), \
         patch("app.tasks.member_sync.store_section_cache",
               new=AsyncMock()) as mock_store:

        # Patch fetch_connector_data in ai_service (imported locally inside the func)
        with patch("app.services.ai_service.fetch_connector_data",
                   new=AsyncMock(return_value=mock_fetch_result)):

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db_inner)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_ctx

            from app.tasks.member_sync import _sync_section_async

            await _sync_section_async(ORG_ID, WORK_EMAIL, DISPLAY_NAME, "emails")

            mock_store.assert_called_once()
            call_kwargs = mock_store.call_args.kwargs
            assert call_kwargs["work_email"] == WORK_EMAIL
            assert call_kwargs["section"] == "emails"
            assert call_kwargs["summary"] == mock_summary


# ── Test _cleanup_async ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_async_calls_both_deletions():
    """cleanup_async calls both delete_expired_cache and delete_inactive_cache."""
    with patch("app.tasks.member_sync.AsyncSessionLocal") as mock_session_cls, \
         patch("app.tasks.member_sync.delete_expired_cache", new=AsyncMock(return_value=5)) as mock_expired, \
         patch("app.tasks.member_sync.delete_inactive_cache", new=AsyncMock(return_value=2)) as mock_inactive:

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        from app.tasks.member_sync import _cleanup_async

        await _cleanup_async()

        mock_expired.assert_called_once()
        mock_inactive.assert_called_once()
        mock_db.commit.assert_called_once()


# ── Test _refresh_active_async ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_active_async_dispatches_tasks():
    """refresh_active_async dispatches sync_member_all_sections for active members."""
    active_pairs = [(ORG_ID, "a@co.com"), (ORG_ID, "b@co.com")]

    with patch("app.tasks.member_sync.AsyncSessionLocal") as mock_session_cls, \
         patch("app.tasks.member_sync.get_active_member_emails", new=AsyncMock(return_value=active_pairs)), \
         patch("app.tasks.member_sync.sync_member_all_sections") as mock_task:

        mock_task.delay = MagicMock()
        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        from app.tasks.member_sync import _refresh_active_async

        await _refresh_active_async()

        assert mock_task.delay.call_count == 2
        call_args_list = mock_task.delay.call_args_list
        dispatched_emails = {c.args[1] for c in call_args_list}
        assert "a@co.com" in dispatched_emails
        assert "b@co.com" in dispatched_emails


# ── Test section query templates ──────────────────────────────────────────────

def test_section_queries_have_all_four_sections():
    from app.tasks.member_sync import _SECTION_QUERIES

    assert set(_SECTION_QUERIES.keys()) == {"emails", "files", "salesforce", "meetings"}


def test_section_queries_contain_limit_or_person_placeholder():
    """
    emails/files/meetings use {limit}; salesforce uses {name} and {work_email}
    since it's person-targeted rather than item-count-limited.
    """
    from app.tasks.member_sync import _SECTION_QUERIES

    limit_sections = ("emails", "files", "meetings")
    person_sections = ("salesforce",)

    for section in limit_sections:
        query = _SECTION_QUERIES[section]
        assert "{limit}" in query, f"Section '{section}' query missing {{limit}} placeholder"

    for section in person_sections:
        query = _SECTION_QUERIES[section]
        assert "{name}" in query or "{work_email}" in query, (
            f"Section '{section}' query missing person placeholder"
        )


def test_section_system_prompts_have_all_four_sections():
    from app.tasks.member_sync import _SECTION_SYSTEM_PROMPTS

    assert set(_SECTION_SYSTEM_PROMPTS.keys()) == {"emails", "files", "salesforce", "meetings"}


def test_section_system_prompts_are_non_empty():
    from app.tasks.member_sync import _SECTION_SYSTEM_PROMPTS

    for section, prompt in _SECTION_SYSTEM_PROMPTS.items():
        assert len(prompt.strip()) > 20, f"Section '{section}' system prompt is too short"
