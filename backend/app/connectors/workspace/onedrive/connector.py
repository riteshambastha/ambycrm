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

        # Extract a meaningful search keyword from the query
        _skip = {
            "show", "get", "find", "fetch", "display", "list", "files", "file",
            "folder", "folders", "onedrive", "drive", "documents", "document",
            "for", "of", "me", "the", "my", "from", "recent", "latest", "all",
            "search", "in", "on", "about", "what", "open", "read",
        }
        keyword_parts = [
            w for w in query.lower().split()
            if w not in _skip and "@" not in w and len(w) > 2
        ]
        keyword = " ".join(keyword_parts[:5]).strip()

        async with httpx.AsyncClient(timeout=30) as client:
            if keyword:
                # Encode apostrophes to avoid OData parse errors
                safe_kw = keyword.replace("'", "''")
                resp = await client.get(
                    f"{_GRAPH_URL}/users/{target_user}/drive/root/search(q='{safe_kw}')",
                    params={
                        "$top": 20,
                        "$select": "id,name,size,lastModifiedDateTime,createdBy,webUrl,file,folder,parentReference",
                    },
                    headers=headers,
                )
            else:
                # List recent items from the root
                resp = await client.get(
                    f"{_GRAPH_URL}/users/{target_user}/drive/root/children",
                    params={
                        "$top": 20,
                        "$select": "id,name,size,lastModifiedDateTime,createdBy,webUrl,file,folder,parentReference",
                        "$orderby": "lastModifiedDateTime desc",
                    },
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
            items = data.get("value", [])
            results: list[dict[str, Any]] = []

            for item in items:
                is_folder = "folder" in item
                name: str = item.get("name", "")
                ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""

                entry: dict[str, Any] = {
                    "name": name,
                    "type": "folder" if is_folder else (item.get("file", {}).get("mimeType") or "file"),
                    "size_bytes": item.get("size"),
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

            return {
                "results": results,
                "source": "onedrive",
                "target_user": target_user,
                "searched_for": keyword or "(recent files)",
            }
