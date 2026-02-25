"""
Microsoft Teams connector — Org-level application permissions.

Uses the same Azure AD app registration as Microsoft 365 / OneDrive.
Requires the Azure AD app to have Application permissions:
  - Calendars.Read.All               ← list any employee's calendar / Teams meetings
  - OnlineMeetings.Read.All          ← resolve meeting ID from joinUrl for transcripts
  - OnlineMeetingTranscript.Read.All ← read transcript content
  - User.Read.All                    ← already granted

Strategy:
  1. Use GET /users/{email}/events?$filter=isOnlineMeeting eq true to list all real
     Teams meetings (requires Calendars.Read.All).
  2. For each event that has a joinUrl, resolve the Graph meeting ID via
     GET /users/{email}/onlineMeetings?$filter=joinWebUrl eq '{url}'.
  3. Fetch transcripts from GET /users/{email}/onlineMeetings/{id}/transcripts.

Grant admin consent in the Azure portal after adding these.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata

_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token"
_GRAPH_URL = "https://graph.microsoft.com/v1.0"
_APP_SCOPE = "https://graph.microsoft.com/.default"

_MAX_TRANSCRIPT_CHARS = 4000


def _parse_vtt(vtt: str) -> str:
    """
    Convert WebVTT transcript to readable plain text.
    Strips WEBVTT header, cue timestamps, cue IDs, and blank lines.
    Merges adjacent lines from the same speaker where possible.
    """
    lines = []
    for line in vtt.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("WEBVTT") or stripped.startswith("NOTE"):
            continue
        if "-->" in stripped:  # timestamp cue
            continue
        if re.fullmatch(r"\d+", stripped):  # cue sequence number
            continue
        lines.append(stripped)
    return " ".join(lines)


def _parse_date_range(query: str) -> tuple[datetime | None, datetime | None]:
    """Parse natural-language date expressions into a (start, end) datetime pair."""
    now = datetime.now(timezone.utc)
    lower = query.lower()

    m = re.search(r"(\d+)\s+years?\s+ago", lower)
    if m:
        n = int(m.group(1))
        mid = now - timedelta(days=365 * n)
        return mid - timedelta(days=183), mid + timedelta(days=183)

    m = re.search(r"older\s+than\s+(\d+)\s+(year|month)s?", lower)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(days=365 * n if unit == "year" else 30 * n)
        return None, now - delta

    m = re.search(r"between\s+(\d{4})\s+and\s+(\d{4})", lower)
    if m:
        y1, y2 = sorted([int(m.group(1)), int(m.group(2))])
        return datetime(y1, 1, 1, tzinfo=timezone.utc), datetime(y2, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    m = re.search(r"(?:before|prior\s+to)\s+(\d{4})", lower)
    if m:
        return None, datetime(int(m.group(1)), 1, 1, tzinfo=timezone.utc)

    m = re.search(r"(?:after|since)\s+(\d{4})", lower)
    if m:
        return datetime(int(m.group(1)), 12, 31, tzinfo=timezone.utc), None

    m = re.search(r"\b(?:in|from)\s+(20\d{2}|19\d{2})\b", lower)
    if not m:
        m = re.search(r"\b(20\d{2}|19\d{2})\b", lower)
    if m:
        y = int(m.group(1))
        return datetime(y, 1, 1, tzinfo=timezone.utc), datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    if "last year" in lower:
        y = now.year - 1
        return datetime(y, 1, 1, tzinfo=timezone.utc), datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    m = re.search(r"last\s+(\d+)\s+months?", lower)
    if m:
        return now - timedelta(days=30 * int(m.group(1))), None

    m = re.search(r"last\s+(\d+)\s+weeks?", lower)
    if m:
        return now - timedelta(weeks=int(m.group(1))), None

    return None, None


class TeamsConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="teams",
        name="Microsoft Teams",
        category="meetings",
        auth_type="client_credentials",
        scope="org",
        description=(
            "Organization-wide Teams access. "
            "Query any employee's meeting recordings and transcripts via Microsoft Graph."
        ),
        icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/Microsoft_Office_Teams_%282018%E2%80%93present%29.svg/120px-Microsoft_Office_Teams_%282018%E2%80%93present%29.svg.png",
        oauth_scopes=[],
        oauth_config={},
    )

    # ------------------------------------------------------------------
    # Client credentials — same Azure AD app as Microsoft 365 / OneDrive
    # ------------------------------------------------------------------

    async def get_org_token(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "scope": _APP_SCOPE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"access_token": data["access_token"], "token_type": data.get("token_type", "Bearer")}

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Teams uses org-level client credentials, not user OAuth")

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError("Teams uses org-level client credentials, not user OAuth")

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return await self.get_org_token()

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        try:
            fresh = await self.get_org_token()
            token = fresh["access_token"]
        except Exception:
            return False
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_GRAPH_URL}/users",
                params={"$top": 1, "$select": "id"},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code == 200

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        target_user: str | None = credentials.get("target_user")
        if not target_user:
            return {
                "results": [],
                "source": "teams",
                "message": (
                    "No target employee specified. "
                    "Ask like: 'Show Teams meetings for john@company.com' or "
                    "'Find meeting transcripts for John Smith'."
                ),
            }

        if "/" in target_user or "\\" in target_user:
            return {"results": [], "source": "teams", "error": "Invalid target user"}

        try:
            fresh = await self.get_org_token()
            token = fresh["access_token"]
        except Exception as exc:
            return {"results": [], "source": "teams", "error": f"Failed to get org token: {exc}"}

        headers = {"Authorization": f"Bearer {token}"}

        # Parse date range; default to last 30 days when nothing specified
        date_start, date_end = _parse_date_range(query)
        if not date_start and not date_end:
            date_start = datetime.now(timezone.utc) - timedelta(days=30)

        # Build Graph $filter for meetings in the date range
        start_str = date_start.strftime("%Y-%m-%dT%H:%M:%SZ") if date_start else None
        end_str = date_end.strftime("%Y-%m-%dT%H:%M:%SZ") if date_end else None

        filters = []
        if start_str:
            filters.append(f"startDateTime ge {start_str}")
        if end_str:
            filters.append(f"startDateTime le {end_str}")
        filter_str = " and ".join(filters)

        # Extract keyword from query (for subject matching)
        _skip = {
            "show", "get", "find", "fetch", "list", "teams", "meeting", "meetings",
            "transcript", "transcripts", "recording", "recordings", "for", "of",
            "the", "my", "from", "recent", "latest", "all", "about", "summary",
            "summarize", "call", "calls",
        }
        keyword_parts = [
            w for w in query.lower().split()
            if w not in _skip and "@" not in w and len(w) > 2 and not w.isdigit()
        ]
        keyword = " ".join(keyword_parts[:4]).strip()

        async with httpx.AsyncClient(timeout=40) as client:
            # ── Step 1: List calendar events that are online meetings ──────
            # /users/{email}/events with isOnlineMeeting eq true covers ALL
            # Teams meetings scheduled via the Teams or Outlook client, unlike
            # /users/{email}/onlineMeetings which only returns Graph-created meetings.
            cal_params: dict[str, Any] = {
                "$top": 20,
                "$select": "subject,start,end,isOnlineMeeting,onlineMeeting,attendees,organizer",
                "$orderby": "start/dateTime desc",
            }

            # Compose $filter — must use start/dateTime format for calendar events
            cal_filters = ["isOnlineMeeting eq true"]
            if start_str:
                cal_filters.append(f"start/dateTime ge '{start_str}'")
            if end_str:
                cal_filters.append(f"start/dateTime le '{end_str}'")
            cal_params["$filter"] = " and ".join(cal_filters)

            resp = await client.get(
                f"{_GRAPH_URL}/users/{target_user}/events",
                params=cal_params,
                headers=headers,
            )

            if resp.status_code == 401:
                return {"results": [], "source": "teams", "error": "Auth failed — org token invalid."}
            if resp.status_code == 403:
                return {
                    "results": [],
                    "source": "teams",
                    "error": (
                        "Permission denied. Ensure your Azure AD app has "
                        "Calendars.Read.All, OnlineMeetings.Read.All, and "
                        "OnlineMeetingTranscript.Read.All Application permissions "
                        "with admin consent."
                    ),
                }
            if resp.status_code == 404:
                return {"results": [], "source": "teams", "error": f"User '{target_user}' not found."}
            if not resp.is_success:
                return {"results": [], "source": "teams", "error": f"Graph API error {resp.status_code}: {resp.text[:200]}"}

            events_data = resp.json().get("value", [])

            # Filter by keyword (subject match) if provided
            if keyword:
                events_data = [
                    e for e in events_data
                    if keyword.lower() in (e.get("subject") or "").lower()
                ]

            results: list[dict[str, Any]] = []

            for event in events_data[:10]:  # cap at 10 to keep response time reasonable
                join_url: str = (event.get("onlineMeeting") or {}).get("joinUrl", "")
                entry: dict[str, Any] = {
                    "subject": event.get("subject") or "Untitled meeting",
                    "start": (event.get("start") or {}).get("dateTime"),
                    "end": (event.get("end") or {}).get("dateTime"),
                    "join_url": join_url,
                    "organizer": (event.get("organizer") or {}).get("emailAddress", {}).get("address", target_user),
                }

                # Extract attendees
                attendees = [
                    (a.get("emailAddress") or {}).get("name")
                    for a in (event.get("attendees") or [])
                ]
                entry["attendees"] = [a for a in attendees if a]

                # ── Step 2: Resolve Graph meeting ID from joinUrl ──────────
                # We need the meeting ID to fetch transcripts. The calendar event
                # has a joinUrl but not the Graph meeting ID directly.
                meeting_id: str = ""
                if join_url:
                    resolve_resp = await client.get(
                        f"{_GRAPH_URL}/users/{target_user}/onlineMeetings",
                        params={"$filter": f"joinWebUrl eq '{join_url}'", "$select": "id"},
                        headers=headers,
                        timeout=10,
                    )
                    if resolve_resp.is_success:
                        matches = resolve_resp.json().get("value", [])
                        if matches:
                            meeting_id = matches[0].get("id", "")

                # ── Step 3: Fetch transcripts ──────────────────────────────
                if meeting_id:
                    trans_resp = await client.get(
                        f"{_GRAPH_URL}/users/{target_user}/onlineMeetings/{meeting_id}/transcripts",
                        headers=headers,
                        timeout=15,
                    )
                    if trans_resp.is_success:
                        transcripts = trans_resp.json().get("value", [])
                        if transcripts:
                            tid = transcripts[0].get("id", "")
                            if tid:
                                content_resp = await client.get(
                                    f"{_GRAPH_URL}/users/{target_user}/onlineMeetings/{meeting_id}/transcripts/{tid}/content",
                                    params={"$format": "text/vtt"},
                                    headers={**headers, "Accept": "text/vtt"},
                                    timeout=20,
                                    follow_redirects=True,
                                )
                                if content_resp.is_success:
                                    plain = _parse_vtt(content_resp.text)
                                    entry["transcript"] = (
                                        plain[:_MAX_TRANSCRIPT_CHARS]
                                        + ("… [truncated]" if len(plain) > _MAX_TRANSCRIPT_CHARS else "")
                                    )
                                    entry["has_transcript"] = True
                            entry["transcript_count"] = len(transcripts)
                        else:
                            entry["has_transcript"] = False
                    else:
                        entry["has_transcript"] = False
                else:
                    entry["has_transcript"] = False

                results.append(entry)

            date_desc = ""
            if date_start and date_end:
                date_desc = f" | {date_start.strftime('%Y-%m-%d')} → {date_end.strftime('%Y-%m-%d')}"
            elif date_start:
                date_desc = f" | since {date_start.strftime('%Y-%m-%d')}"

            return {
                "results": results,
                "source": "teams",
                "target_user": target_user,
                "searched_for": (keyword or "(recent meetings)") + date_desc,
            }
