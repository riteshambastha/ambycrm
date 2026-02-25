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
    """Can we list Teams online meetings for a specific user? (OnlineMeetings.Read.All)"""
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{GRAPH_URL}/users/{email}/onlineMeetings",
            params={
                "$top": 3,
                "$select": "subject,startDateTime",
                "$filter": f"startDateTime ge {start}",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            meetings = resp.json().get("value", [])
            subjects = [m.get("subject", "(no subject)") for m in meetings]
            return True, f"{len(meetings)} meeting(s) found (last 30 days). Subjects: {subjects}"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


async def check_teams_transcript_permission(token: str, email: str) -> tuple[bool, str]:
    """
    Verify OnlineMeetingTranscript.Read.All is granted by checking the
    transcripts endpoint on the first available meeting (if any).
    Returns SKIP if no meetings are available to test against.
    """
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=20) as client:
        # Get the first meeting
        resp = await client.get(
            f"{GRAPH_URL}/users/{email}/onlineMeetings",
            params={"$top": 1, "$select": "id,subject", "$filter": f"startDateTime ge {start}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if not resp.is_success:
            return False, f"Could not fetch meetings to test transcripts: HTTP {resp.status_code}"

        meetings = resp.json().get("value", [])
        if not meetings:
            return None, "No meetings found in the last 90 days — cannot test transcript permission"

        meeting_id = meetings[0]["id"]
        subject = meetings[0].get("subject", "?")

        # Try to list transcripts
        tr = await client.get(
            f"{GRAPH_URL}/users/{email}/onlineMeetings/{meeting_id}/transcripts",
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
