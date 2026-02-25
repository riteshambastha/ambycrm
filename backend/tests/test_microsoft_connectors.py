"""
Microsoft Connector Health Check
=================================
Tests that the three org-level Microsoft connectors — Microsoft 365 (mail),
OneDrive, and Teams — can authenticate and reach the Graph API.

Run from the backend directory with the .env loaded:

    cd backend
    set -a && source ../.env && set +a
    python -m pytest tests/test_microsoft_connectors.py -v

Or run directly:

    cd backend
    set -a && source ../.env && set +a
    python tests/test_microsoft_connectors.py
"""

import asyncio
import os
import sys

import httpx

# ---------------------------------------------------------------------------
# Config — read from environment (loaded from .env before running)
# ---------------------------------------------------------------------------

CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")

TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH_URL = "https://graph.microsoft.com/v1.0"
APP_SCOPE = "https://graph.microsoft.com/.default"

# Put a real employee email here to test per-user queries (mail / OneDrive / Teams)
# Falls back to just checking token + user list if not set.
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "")  # e.g. alpesh@nailbiter.com

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⚠️  SKIP"


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

async def get_org_token() -> str:
    """Obtain a fresh application-level access token via client credentials."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": APP_SCOPE,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

async def check_token() -> tuple[bool, str]:
    """Can we obtain a client credentials access token at all?"""
    if not CLIENT_ID or not CLIENT_SECRET or not TENANT_ID:
        return False, "MICROSOFT_CLIENT_ID / SECRET / TENANT_ID not set in environment"
    try:
        token = await get_org_token()
        return bool(token), f"Token obtained (first 20 chars): {token[:20]}…"
    except Exception as exc:
        return False, str(exc)


async def check_user_list(token: str) -> tuple[bool, str]:
    """Can we list users in the tenant? (User.Read.All)"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{GRAPH_URL}/users",
            params={"$top": 3, "$select": "displayName,mail"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            users = resp.json().get("value", [])
            names = [u.get("displayName", "?") for u in users]
            return True, f"Found users: {names}"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


async def check_mail(token: str, email: str) -> tuple[bool, str]:
    """Can we read mail for a specific user? (Mail.Read)"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{GRAPH_URL}/users/{email}/messages",
            params={"$top": 3, "$select": "subject,receivedDateTime"},
            headers={
                "Authorization": f"Bearer {token}",
                "Prefer": 'outlook.body-content-type="text"',
            },
        )
        if resp.status_code == 200:
            msgs = resp.json().get("value", [])
            subjects = [m.get("subject", "(no subject)") for m in msgs]
            return True, f"{len(msgs)} message(s) fetched. Subjects: {subjects}"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


async def check_onedrive(token: str, email: str) -> tuple[bool, str]:
    """Can we list OneDrive root files for a specific user? (Files.Read.All)"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{GRAPH_URL}/users/{email}/drive/root/children",
            params={"$top": 3, "$select": "name,lastModifiedDateTime"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            items = resp.json().get("value", [])
            names = [i.get("name", "?") for i in items]
            return True, f"{len(items)} item(s) found. Names: {names}"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


async def check_teams(token: str, email: str) -> tuple[bool, str]:
    """
    Can we list Teams calendar meetings for a user? (Calendars.Read.All)
    Uses /users/{email}/events?$filter=isOnlineMeeting eq true, which returns
    all real Teams meetings scheduled via Teams or Outlook — unlike
    /users/{email}/onlineMeetings which only returns Graph-API-created meetings.
    """
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{GRAPH_URL}/users/{email}/events",
            params={
                "$top": 20,
                "$select": "subject,start,isOnlineMeeting,onlineMeeting",
                "$filter": f"start/dateTime ge '{start}'",
                "$orderby": "start/dateTime desc",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            all_events = resp.json().get("value", [])
            # isOnlineMeeting is not server-side filterable — filter client-side
            meetings = [e for e in all_events if e.get("isOnlineMeeting") or e.get("onlineMeeting")]
            subjects = [m.get("subject", "(no subject)") for m in meetings[:3]]
            return True, f"{len(meetings)} Teams meeting(s) found (last 30 days). Subjects: {subjects}"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


async def check_teams_transcript_permission(token: str, email: str) -> tuple[bool, str]:
    """
    Verify OnlineMeetingTranscript.Read.All is granted.
    Finds the first Teams calendar meeting with a joinUrl, resolves its
    Graph meeting ID, then checks the transcripts endpoint.
    """
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=20) as client:
        # Get recent calendar events and filter client-side for online meetings
        resp = await client.get(
            f"{GRAPH_URL}/users/{email}/events",
            params={
                "$top": 20,
                "$select": "subject,start,isOnlineMeeting,onlineMeeting",
                "$filter": f"start/dateTime ge '{start}'",
                "$orderby": "start/dateTime desc",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if not resp.is_success:
            return False, f"Could not fetch calendar meetings: HTTP {resp.status_code}"

        events = resp.json().get("value", [])
        # isOnlineMeeting is not server-side filterable — filter client-side
        online = [e for e in events if e.get("isOnlineMeeting") or e.get("onlineMeeting")]
        # Find one with a joinUrl so we can resolve the meeting ID
        join_url = ""
        subject = ""
        for ev in online:
            join_url = (ev.get("onlineMeeting") or {}).get("joinUrl", "")
            subject = ev.get("subject", "?")
            if join_url:
                break

        if not join_url:
            return None, "No Teams meetings with a joinUrl found in the last 90 days — cannot test transcript permission"

        # Extract organizer's Azure AD object ID from the joinUrl context
        import urllib.parse, json as _json
        organizer_id = ""
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(join_url).query)
            ctx = _json.loads(urllib.parse.unquote(qs.get("context", [""])[0]))
            organizer_id = ctx.get("Oid", "")
        except Exception:
            pass

        # Resolve Graph meeting ID via organizer's account (not attendee's)
        lookup_user = organizer_id or email
        resolve = await client.get(
            f"{GRAPH_URL}/users/{lookup_user}/onlineMeetings",
            params={"$filter": f"joinWebUrl eq '{join_url}'"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if not resolve.is_success:
            return False, f"Could not resolve meeting ID from joinUrl (organizer={lookup_user}): HTTP {resolve.status_code}: {resolve.text[:150]}"
        matches = resolve.json().get("value", [])
        if not matches:
            return None, f"No Graph meeting ID found for '{subject}' — transcript check skipped"
        meeting_id = matches[0]["id"]

        # Check the transcript endpoint via organizer's account
        transcript_user = organizer_id or email
        tr = await client.get(
            f"{GRAPH_URL}/users/{transcript_user}/onlineMeetings/{meeting_id}/transcripts",
            headers={"Authorization": f"Bearer {token}"},
        )
        if tr.status_code == 200:
            count = len(tr.json().get("value", []))
            return True, f"Transcript endpoint accessible for '{subject}' — {count} transcript(s)"
        if tr.status_code == 403:
            return False, "HTTP 403 — OnlineMeetingTranscript.Read.All permission missing or not consented"
        return False, f"HTTP {tr.status_code}: {tr.text[:200]}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all() -> None:
    print("\n" + "=" * 60)
    print("  Microsoft Connector Health Check")
    print("=" * 60)

    # 1. Token
    print("\n[1] Client Credentials Token")
    ok, msg = await check_token()
    print(f"  {PASS if ok else FAIL}  {msg}")
    if not ok:
        print("\n  Cannot continue without a valid token. Check your .env values.")
        sys.exit(1)

    token = await get_org_token()

    # 2. User list (User.Read.All)
    print("\n[2] User.Read.All — list tenant users")
    ok, msg = await check_user_list(token)
    print(f"  {PASS if ok else FAIL}  {msg}")

    # Per-user checks
    if not TEST_USER_EMAIL:
        print(f"\n  {SKIP}  TEST_USER_EMAIL not set — skipping per-user checks.")
        print("  Set it in your .env or shell:  export TEST_USER_EMAIL=alpesh@nailbiter.com")
    else:
        email = TEST_USER_EMAIL
        print(f"\n  Using test user: {email}\n")

        # 3. Mail
        print("[3] Mail.Read — read mailbox")
        ok, msg = await check_mail(token, email)
        print(f"  {PASS if ok else FAIL}  {msg}")

        # 4. OneDrive
        print("\n[4] Files.Read.All — list OneDrive root")
        ok, msg = await check_onedrive(token, email)
        print(f"  {PASS if ok else FAIL}  {msg}")

        # 5. Teams meetings
        print("\n[5] OnlineMeetings.Read.All — list Teams meetings")
        ok, msg = await check_teams(token, email)
        print(f"  {PASS if ok else FAIL}  {msg}")

        # 6. Teams transcripts
        print("\n[6] OnlineMeetingTranscript.Read.All — access transcript endpoint")
        ok, msg = await check_teams_transcript_permission(token, email)
        if ok is None:
            print(f"  {SKIP}  {msg}")
        else:
            print(f"  {PASS if ok else FAIL}  {msg}")

    print("\n" + "=" * 60 + "\n")


# ---------------------------------------------------------------------------
# pytest-compatible wrappers (optional — works with both pytest and direct run)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402 — only needed when run via pytest


@pytest.mark.asyncio
async def test_token():
    ok, msg = await check_token()
    assert ok, msg


@pytest.mark.asyncio
async def test_user_list():
    token = await get_org_token()
    ok, msg = await check_user_list(token)
    assert ok, msg


@pytest.mark.asyncio
@pytest.mark.skipif(not TEST_USER_EMAIL, reason="TEST_USER_EMAIL not set")
async def test_mail():
    token = await get_org_token()
    ok, msg = await check_mail(token, TEST_USER_EMAIL)
    assert ok, msg


@pytest.mark.asyncio
@pytest.mark.skipif(not TEST_USER_EMAIL, reason="TEST_USER_EMAIL not set")
async def test_onedrive():
    token = await get_org_token()
    ok, msg = await check_onedrive(token, TEST_USER_EMAIL)
    assert ok, msg


@pytest.mark.asyncio
@pytest.mark.skipif(not TEST_USER_EMAIL, reason="TEST_USER_EMAIL not set")
async def test_teams_meetings():
    """Requires Calendars.Read.All application permission in Azure AD."""
    token = await get_org_token()
    ok, msg = await check_teams(token, TEST_USER_EMAIL)
    assert ok, msg


@pytest.mark.asyncio
@pytest.mark.skipif(not TEST_USER_EMAIL, reason="TEST_USER_EMAIL not set")
async def test_teams_transcripts():
    token = await get_org_token()
    ok, msg = await check_teams_transcript_permission(token, TEST_USER_EMAIL)
    if ok is None:
        pytest.skip(msg)
    assert ok, msg


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(run_all())
