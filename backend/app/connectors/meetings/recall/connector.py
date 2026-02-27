"""
Recall.ai connector — API key auth.

Recall.ai is a "notetaker bot" platform. You send a bot to any Zoom/Teams/Meet
meeting URL and it records + transcribes automatically.

API docs: https://docs.recall.ai/reference

Requires in .env:
  RECALL_API_KEY   — your Recall.ai API key
  RECALL_BASE_URL  — e.g. https://us-west-2.recall.ai

fetch_data returns:
  - List of recent bots (recordings) with status, meeting URL, start time
  - Full transcript words for each completed bot (up to MAX_TRANSCRIPT chars)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.connectors.base import BaseConnector, ConnectorMetadata

logger = logging.getLogger(__name__)


def _api_key() -> str:
    return settings.RECALL_API_KEY


def _api_url() -> str:
    return f"{settings.RECALL_BASE_URL.rstrip('/')}/api/v1"
_MAX_TRANSCRIPT_CHARS = 3000


def _fmt_transcript(words: list[dict]) -> str:
    """Convert Recall word-level transcript to readable text grouped by speaker."""
    if not words:
        return ""
    lines: list[str] = []
    current_speaker = ""
    current_words: list[str] = []
    for w in words:
        speaker = (w.get("speaker") or {}).get("name") or "Speaker"
        text = w.get("text", "").strip()
        if not text:
            continue
        if speaker != current_speaker:
            if current_words:
                lines.append(f"{current_speaker}: {' '.join(current_words)}")
            current_speaker = speaker
            current_words = [text]
        else:
            current_words.append(text)
    if current_words:
        lines.append(f"{current_speaker}: {' '.join(current_words)}")
    return "\n".join(lines)


def _parse_date_range(query: str) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    lower = query.lower()

    m = re.search(r"last\s+(\d+)\s+days?", lower)
    if m:
        return now - timedelta(days=int(m.group(1))), None

    m = re.search(r"last\s+(\d+)\s+weeks?", lower)
    if m:
        return now - timedelta(weeks=int(m.group(1))), None

    m = re.search(r"last\s+(\d+)\s+months?", lower)
    if m:
        return now - timedelta(days=30 * int(m.group(1))), None

    if "today" in lower:
        return now.replace(hour=0, minute=0, second=0), None
    if "yesterday" in lower:
        yesterday = now - timedelta(days=1)
        return yesterday.replace(hour=0, minute=0, second=0), yesterday.replace(hour=23, minute=59, second=59)
    if "this week" in lower:
        return now - timedelta(days=now.weekday()), None

    return None, None


class RecallConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="recall",
        name="Recall.ai",
        category="meetings",
        auth_type="api_key",
        scope="org",
        description="Access recordings and transcripts from meetings recorded by Recall.ai notetaker bots.",
        icon_url="/icons/recall.svg",
        oauth_scopes=[],
        oauth_config={},
    )

    # ------------------------------------------------------------------
    # API key auth — no OAuth redirect, no stored token needed
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {_api_key()}"}

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Recall.ai uses API key auth, not OAuth")

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError("Recall.ai uses API key auth, not OAuth")

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return credentials

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        if not _api_key():
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_api_url()}/bot/",
                    params={"limit": 1},
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        if not _api_key():
            return {"results": [], "source": "recall", "error": "RECALL_API_KEY not set in .env"}

        target_user: str | None = credentials.get("target_user")
        lower = query.lower()

        # Parse explicit count
        count_match = re.search(r"\b(\d+)\b", query)
        limit = min(int(count_match.group(1)), 50) if count_match else 10

        # Parse date range
        date_start, date_end = _parse_date_range(query)

        # Extract keyword for meeting name/URL matching
        _stop = {
            "show", "get", "find", "list", "recall", "meeting", "meetings",
            "recording", "recordings", "transcript", "transcripts", "bot",
            "bots", "notetaker", "latest", "recent", "all", "for", "me",
            "my", "the", "from", "can", "you", "please",
        }
        keyword_parts = [
            w for w in lower.split()
            if w not in _stop and "@" not in w and len(w) > 2 and not w.isdigit()
        ]
        keyword = " ".join(keyword_parts[:3]).strip()

        # When a target_user is set, derive the person's name for transcript matching
        target_name_lower: str = ""
        if target_user:
            local_part = target_user.split("@")[0]
            target_name_lower = local_part.replace(".", " ").replace("_", " ").replace("-", " ").lower()

        # Build query params — fetch more bots when person-filtering so we have a
        # better chance of finding meetings that mention the target person
        fetch_limit = max(limit, 25) if target_user else limit
        params: dict[str, Any] = {"limit": fetch_limit}
        if date_start:
            params["join_at__gte"] = date_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        if date_end:
            params["join_at__lte"] = date_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_api_url()}/bot/",
                params=params,
                headers=self._headers(),
            )

            if resp.status_code == 401:
                return {"results": [], "source": "recall", "error": "Invalid Recall.ai API key."}
            if not resp.is_success:
                return {"results": [], "source": "recall", "error": f"Recall API error {resp.status_code}: {resp.text[:200]}"}

            bots = resp.json().get("results", [])
            logger.info("[Recall] Fetched %d bots (target_user=%s)", len(bots), target_user or "none")

            # When NOT doing a person-specific query, filter by keyword in bot_name/meeting_url
            if keyword and not target_user:
                bots = [
                    b for b in bots
                    if keyword in (b.get("bot_name") or "").lower()
                    or keyword in (b.get("meeting_url") or "").lower()
                ]

            results: list[dict[str, Any]] = []

            for bot in bots:
                bot_id = bot.get("id", "")
                status_changes = bot.get("status_changes") or []
                current_status = status_changes[-1].get("code", "unknown") if status_changes else "unknown"
                join_at = bot.get("join_at") or bot.get("created_at", "")

                entry: dict[str, Any] = {
                    "id": bot_id,
                    "name": bot.get("bot_name") or "Unnamed meeting",
                    "meeting_url": bot.get("meeting_url", ""),
                    "status": current_status,
                    "started_at": join_at,
                    "has_transcript": current_status == "done",
                }

                # Fetch transcript for completed recordings
                if current_status == "done" and bot_id:
                    tr = await client.get(
                        f"{_api_url()}/bot/{bot_id}/transcript/",
                        headers=self._headers(),
                        timeout=20,
                    )
                    if tr.is_success:
                        words = tr.json()
                        plain = _fmt_transcript(words) if isinstance(words, list) else ""
                        if plain:
                            entry["transcript"] = (
                                plain[:_MAX_TRANSCRIPT_CHARS]
                                + ("… [truncated]" if len(plain) > _MAX_TRANSCRIPT_CHARS else "")
                            )
                            entry["word_count"] = len(words)

                results.append(entry)

            # When target_user is set, keep only recordings where the person
            # is mentioned in the transcript or bot_name (i.e. they participated)
            if target_user and results:
                person_results = []
                for r in results:
                    transcript_text = (r.get("transcript") or "").lower()
                    bot_name = (r.get("name") or "").lower()
                    meeting_url = (r.get("meeting_url") or "").lower()
                    match = (
                        target_user.lower() in transcript_text
                        or target_user.lower() in bot_name
                        or target_user.lower() in meeting_url
                    )
                    if not match and target_name_lower:
                        name_parts = target_name_lower.split()
                        match = any(
                            part in transcript_text or part in bot_name
                            for part in name_parts if len(part) > 2
                        )
                    if match:
                        person_results.append(r)

                logger.info(
                    "[Recall] Person filter: %d/%d recordings match '%s'",
                    len(person_results), len(results), target_user,
                )
                # If person filter yields nothing, fall back to ALL recordings
                # so the LLM at least has some meeting context
                if person_results:
                    results = person_results

            if not results:
                return {
                    "results": [],
                    "source": "recall",
                    "target_user": target_user,
                    "message": (
                        "No Recall.ai recordings found. "
                        "Send a bot to a meeting first: go to https://recall.ai and create a bot, "
                        "or use the Recall.ai API to dispatch a bot to a meeting URL."
                    ),
                }

            return {
                "results": results[:limit],
                "source": "recall",
                "target_user": target_user,
                "searched_for": keyword or "(recent recordings)",
                "total": len(results),
            }
