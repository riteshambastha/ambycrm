"""
OneDrive connector — Org-level application permissions.

Uses the same Azure AD app registration as Microsoft 365 (client credentials flow).
Requires the Azure AD app to have Application permissions:
  - Files.Read.All        ← new permission needed
  - User.Read.All         ← already granted for Microsoft 365

Once connected, the AI service can query any employee's OneDrive files,
folders, and document contents.
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

# Fetch and return full text for these file types
_TEXT_READABLE = {".txt", ".md", ".csv", ".json", ".log", ".xml", ".yaml", ".yml", ".py", ".js", ".ts"}

# Try Graph format-conversion for Office files (returns text/html, then strip to plain)
_OFFICE_READABLE = {".docx", ".doc"}

# Cap content per file to avoid flooding the LLM context window
_MAX_CONTENT_CHARS = 2000
# Skip fetching content for files larger than this
_MAX_FETCH_SIZE_BYTES = 512 * 1024  # 512 KB


def _parse_date_range(query: str) -> tuple[datetime | None, datetime | None]:
    """
    Parse natural-language date constraints from a query string.
    Returns (start, end) — either may be None (open-ended).

    Supports:
      "5 years ago"           → window around that year
      "older than 3 years"    → anything before 3 years ago
      "before 2021"           → anything before 2021-01-01
      "after 2019"            → anything after 2019-12-31
      "since 2022"            → anything after 2022-01-01
      "in 2020" / "from 2020" → full calendar year 2020
      "last year"             → full previous calendar year
      "last 6 months"         → past 6 months
      "between 2018 and 2021" → inclusive year range
    """
    now = datetime.now(timezone.utc)
    lower = query.lower()

    # "N years ago" — give a ±6-month window around that year
    m = re.search(r"(\d+)\s+years?\s+ago", lower)
    if m:
        n = int(m.group(1))
        mid = now - timedelta(days=365 * n)
        return mid - timedelta(days=183), mid + timedelta(days=183)

    # "older than N years / months"
    m = re.search(r"older\s+than\s+(\d+)\s+(year|month)s?", lower)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(days=365 * n) if unit == "year" else timedelta(days=30 * n)
        return None, now - delta

    # "more than N years old"
    m = re.search(r"more\s+than\s+(\d+)\s+years?\s+old", lower)
    if m:
        n = int(m.group(1))
        return None, now - timedelta(days=365 * n)

    # "between YEAR and YEAR"
    m = re.search(r"between\s+(\d{4})\s+and\s+(\d{4})", lower)
    if m:
        y1, y2 = sorted([int(m.group(1)), int(m.group(2))])
        return datetime(y1, 1, 1, tzinfo=timezone.utc), datetime(y2, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # "before YEAR / prior to YEAR"
    m = re.search(r"(?:before|prior\s+to)\s+(\d{4})", lower)
    if m:
        return None, datetime(int(m.group(1)), 1, 1, tzinfo=timezone.utc)

    # "after YEAR / since YEAR"
    m = re.search(r"(?:after|since)\s+(\d{4})", lower)
    if m:
        return datetime(int(m.group(1)), 12, 31, 23, 59, 59, tzinfo=timezone.utc), None

    # "in YEAR" or "from YEAR" (standalone 4-digit year)
    m = re.search(r"\b(?:in|from)\s+(\d{4})\b", lower)
    if not m:
        m = re.search(r"\b(20\d{2}|19\d{2})\b", lower)  # bare year like "2019 files"
    if m:
        y = int(m.group(1))
        return datetime(y, 1, 1, tzinfo=timezone.utc), datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # "last year"
    if "last year" in lower:
        y = now.year - 1
        return datetime(y, 1, 1, tzinfo=timezone.utc), datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # "last N months"
    m = re.search(r"last\s+(\d+)\s+months?", lower)
    if m:
        return now - timedelta(days=30 * int(m.group(1))), None

    return None, None


def _in_date_range(item: dict[str, Any], start: datetime | None, end: datetime | None) -> bool:
    """Return True if the item's createdDateTime or lastModifiedDateTime falls in [start, end]."""
    raw = item.get("createdDateTime") or item.get("lastModifiedDateTime") or ""
    if not raw:
        return True  # can't filter — include it
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if start and dt < start:
            return False
        if end and dt > end:
            return False
        return True
    except Exception:
        return True


class OneDriveConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="onedrive",
        name="OneDrive",
        category="workspace",
        auth_type="client_credentials",
        scope="org",
        description=(
            "Organization-wide OneDrive access. "
            "Query, search, and read employee files and folders via Microsoft Graph."
        ),
        icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/OneDrive_icon.svg/120px-OneDrive_icon.svg.png",
        oauth_scopes=[],
        oauth_config={},
    )

    # ------------------------------------------------------------------
    # Client credentials — same Azure AD app as Microsoft 365
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
            return {
                "access_token": data["access_token"],
                "token_type": data.get("token_type", "Bearer"),
            }

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("OneDrive uses org-level client credentials, not user OAuth")

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError("OneDrive uses org-level client credentials, not user OAuth")

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
                "source": "onedrive",
                "message": (
                    "No target employee specified. "
                    "Ask like: 'Show OneDrive files for john@company.com' or "
                    "'Find files for John Smith'."
                ),
            }

        if "/" in target_user or "\\" in target_user:
            return {"results": [], "source": "onedrive", "error": "Invalid target user"}

        try:
            fresh = await self.get_org_token()
            token = fresh["access_token"]
        except Exception as exc:
            return {"results": [], "source": "onedrive", "error": f"Failed to get org token: {exc}"}

        headers = {"Authorization": f"Bearer {token}"}

        # Parse any date constraints from the query
        date_start, date_end = _parse_date_range(query)
        has_date_filter = date_start is not None or date_end is not None

        # Extract a meaningful content keyword (strip navigation + date words)
        _skip = {
            "show", "get", "find", "fetch", "display", "list", "files", "file",
            "folder", "folders", "onedrive", "drive", "documents", "document",
            "for", "of", "me", "the", "my", "from", "recent", "latest", "all",
            "search", "in", "on", "about", "what", "open", "read",
            # date stop-words
            "year", "years", "month", "months", "ago", "old", "older", "than",
            "before", "after", "since", "between", "last", "prior",
        }
        keyword_parts = [
            w for w in query.lower().split()
            if w not in _skip and "@" not in w and len(w) > 2 and not w.isdigit()
        ]
        keyword = " ".join(keyword_parts[:5]).strip()

        # When filtering by date, fetch more results so client-side filter has enough to work with
        top = 100 if has_date_filter else 20

        _select = "id,name,size,lastModifiedDateTime,createdDateTime,createdBy,webUrl,file,folder,parentReference"

        async with httpx.AsyncClient(timeout=30) as client:
            if keyword:
                safe_kw = keyword.replace("'", "''")
                resp = await client.get(
                    f"{_GRAPH_URL}/users/{target_user}/drive/root/search(q='{safe_kw}')",
                    params={"$top": top, "$select": _select},
                    headers=headers,
                )
            elif has_date_filter:
                # No content keyword but we have a date filter — search all files broadly
                # using the year as a broad search term so we cover subfolders too
                year_hint = ""
                if date_end:
                    year_hint = str(date_end.year)
                elif date_start:
                    year_hint = str(date_start.year)
                # Empty-string search is not allowed; fall back to listing root with higher top
                if year_hint:
                    resp = await client.get(
                        f"{_GRAPH_URL}/users/{target_user}/drive/root/search(q='{year_hint}')",
                        params={"$top": top, "$select": _select},
                        headers=headers,
                    )
                else:
                    resp = await client.get(
                        f"{_GRAPH_URL}/users/{target_user}/drive/root/children",
                        params={"$top": top, "$select": _select, "$orderby": "lastModifiedDateTime desc"},
                        headers=headers,
                    )
            else:
                # No keyword, no date — list root folder, most recent first
                resp = await client.get(
                    f"{_GRAPH_URL}/users/{target_user}/drive/root/children",
                    params={"$top": top, "$select": _select, "$orderby": "lastModifiedDateTime desc"},
                    headers=headers,
                )

            if resp.status_code == 401:
                return {"results": [], "source": "onedrive", "error": "Auth failed — org token invalid."}
            if resp.status_code == 404:
                return {
                    "results": [],
                    "source": "onedrive",
                    "error": f"User '{target_user}' not found or has no OneDrive.",
                }
            if resp.status_code == 403:
                return {
                    "results": [],
                    "source": "onedrive",
                    "error": (
                        "Permission denied. Ensure your Azure AD app has "
                        "Files.Read.All (Application) permission with admin consent granted."
                    ),
                }
            if not resp.is_success:
                return {"results": [], "source": "onedrive", "error": f"Graph API error {resp.status_code}: {resp.text[:200]}"}

            data = resp.json()
            raw_items = data.get("value", [])

            # Apply client-side date filter
            items = (
                [i for i in raw_items if _in_date_range(i, date_start, date_end)]
                if has_date_filter
                else raw_items
            )
            results: list[dict[str, Any]] = []

            for item in items:
                is_folder = "folder" in item
                name: str = item.get("name", "")
                ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""

                entry: dict[str, Any] = {
                    "name": name,
                    "type": "folder" if is_folder else (item.get("file", {}).get("mimeType") or "file"),
                    "size_bytes": item.get("size"),
                    "created": item.get("createdDateTime"),
                    "modified": item.get("lastModifiedDateTime"),
                    "web_url": item.get("webUrl"),
                    "path": item.get("parentReference", {}).get("path", "").replace("/drive/root:", "") or "/",
                    "created_by": ((item.get("createdBy") or {}).get("user") or {}).get("displayName"),
                }

                item_id: str | None = item.get("id")
                file_size = item.get("size") or 0

                # Fetch content for readable file types within size limit
                if not is_folder and item_id and file_size < _MAX_FETCH_SIZE_BYTES:
                    content: str | None = None

                    if ext in _TEXT_READABLE:
                        try:
                            cr = await client.get(
                                f"{_GRAPH_URL}/users/{target_user}/drive/items/{item_id}/content",
                                headers=headers,
                                follow_redirects=True,
                                timeout=20,
                            )
                            if cr.is_success:
                                raw = cr.text
                                content = raw[:_MAX_CONTENT_CHARS] + ("… [truncated]" if len(raw) > _MAX_CONTENT_CHARS else "")
                        except Exception:
                            pass

                    elif ext in _OFFICE_READABLE:
                        # Word docs: download and let Graph convert to text
                        try:
                            cr = await client.get(
                                f"{_GRAPH_URL}/users/{target_user}/drive/items/{item_id}/content",
                                params={"format": "text"},
                                headers=headers,
                                follow_redirects=True,
                                timeout=20,
                            )
                            if cr.is_success:
                                raw = cr.text
                                content = raw[:_MAX_CONTENT_CHARS] + ("… [truncated]" if len(raw) > _MAX_CONTENT_CHARS else "")
                        except Exception:
                            pass

                    if content:
                        entry["content"] = content

                results.append(entry)

            # Build a human-readable description of any date filter applied
            date_desc = ""
            if date_start and date_end:
                date_desc = f" | date range: {date_start.strftime('%Y-%m-%d')} → {date_end.strftime('%Y-%m-%d')}"
            elif date_end:
                date_desc = f" | before {date_end.strftime('%Y-%m-%d')}"
            elif date_start:
                date_desc = f" | after {date_start.strftime('%Y-%m-%d')}"

            return {
                "results": results,
                "source": "onedrive",
                "target_user": target_user,
                "searched_for": (keyword or "(all files)") + date_desc,
            }
