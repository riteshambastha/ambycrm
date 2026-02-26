"""
AI orchestration service.
Handles intent detection, parallel connector data fetching, and LLM streaming.
"""

import asyncio
import json
import re
from typing import Any, AsyncIterator

import litellm

from app.config import settings
from app.connectors.registry import registry

# Which connector keys map to which intent keywords
_CONNECTOR_INTENT_MAP: dict[str, list[str]] = {
    "salesforce": ["salesforce", "deal", "opportunity", "crm", "pipeline", "account"],
    "hubspot": ["hubspot", "contact", "company"],
    "dynamics": ["dynamics", "microsoft crm"],
    "sugarcrm": ["sugarcrm", "sugar"],
    "google_workspace": ["gmail", "google drive", "google docs"],
    "microsoft365": [
        "outlook", "office 365",
        "email", "emails", "inbox", "mail", "message",
        "microsoft email", "microsoft mail",
    ],
    "onedrive": [
        "onedrive", "one drive", "sharepoint",
        "file", "files", "folder", "folders", "document", "documents",
        "spreadsheet", "presentation", "word doc", "excel", "powerpoint",
        "upload", "attachment", "drive",
    ],
    "fireflies": ["fireflies", "transcript", "recording", "call summary"],
    "teams": ["teams", "microsoft teams"],
    "otter": ["otter", "otter.ai"],
    "recall": ["recall", "recall.ai"],
    # Generic terms that could apply to any meeting connector
    "meeting": ["meeting", "meetings", "summary", "summarize my meeting"],
}

_SYSTEM_PROMPT = """You are AmbyChat, an AI assistant that has access to enterprise tools like CRMs, email, OneDrive files, documents, and Teams meeting transcripts.

When answering, you have been provided with relevant data fetched from connected integrations.
Always:
- Cite the source of data (e.g., "From Outlook:", "From OneDrive:", "From Teams:", "From Salesforce:").
- Be concise and structured. Use markdown lists and headings where helpful.
- For OneDrive files, include the file name and web URL so the user can open it directly.
- For OneDrive VIDEO files (is_video: true), you MUST emit a special playback marker on its own line:
  [VIDEO:owner_email|item_id|filename]
  Replace owner_email, item_id, and filename with the actual values from the data.
  Example: [VIDEO:amit@company.com|AAB3X9!456|Meeting Recording.mp4]
  This marker renders an inline video player in the chat UI.
- For Teams meetings, include the meeting subject, date, and key points from the transcript if available.
- If a meeting has no transcript (has_transcript: false), note it was not recorded or transcription was not enabled.
- If data is missing or unavailable, say so clearly.
"""


_MEETING_CONNECTORS = {"fireflies", "teams", "otter", "recall"}


def detect_connectors(message: str) -> list[str]:
    """Heuristically detect which connectors are relevant to the message."""
    lower = message.lower()
    matched: list[str] = []
    for key, keywords in _CONNECTOR_INTENT_MAP.items():
        if key == "meeting":
            # generic meeting terms → expand to all meeting connectors
            if any(kw in lower for kw in keywords):
                matched.extend(_MEETING_CONNECTORS)
            continue
        if any(kw in lower for kw in keywords):
            matched.append(key)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for k in matched:
        if k not in seen:
            seen.add(k)
            result.append(k)
    # Return None-equivalent (empty list) to signal "try all" when nothing matched
    return result


def _extract_target_from_text(
    text: str,
    org_members: list[dict[str, Any]] | None,
) -> str | None:
    """Extract a target user email from a single text string (no history fallback)."""
    email_match = re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", text)
    if email_match:
        return email_match.group(0).lower()
    if org_members:
        lower = text.lower()
        for member in org_members:
            work_email = member.get("work_email")
            if not work_email:
                continue
            first = (member.get("first_name") or "").strip().lower()
            last = (member.get("last_name") or "").strip().lower()
            full = f"{first} {last}".strip()
            if full and full in lower:
                return work_email
            if first and len(first) > 3 and first in lower:
                return work_email
    return None


def extract_target_user(
    message: str,
    org_members: list[dict[str, Any]] | None = None,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    """
    Extract a target user email from the current message, falling back to
    recent conversation history so follow-up questions work correctly.

    Priority:
    1. Explicit email address in current message.
    2. Known employee name in current message.
    3. Email / name found in the last 10 conversation turns (most recent first).

    This means "which is the most urgent?" following "show emails for john@acme.com"
    will correctly resolve john@acme.com as the target.
    """
    # Current message first
    target = _extract_target_from_text(message, org_members)
    if target:
        return target

    # Fall back to scanning recent history (newest messages first)
    if history:
        for msg in reversed(history[-10:]):
            content = msg.get("content", "")
            target = _extract_target_from_text(content, org_members)
            if target:
                return target

    return None


async def fetch_connector_data(
    connector_key: str,
    credentials: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    """Fetch data from a single connector, catching errors gracefully."""
    connector = registry.get_instance(connector_key)
    if not connector:
        return {"connector": connector_key, "error": "Connector not found", "results": []}
    try:
        data = await connector.fetch_data(credentials, query)
        return {"connector": connector_key, **data}
    except Exception as exc:
        return {"connector": connector_key, "error": str(exc), "results": []}


async def fetch_all_connector_data(
    connected_integrations: list[dict[str, Any]],  # [{connector_key, credentials_dict}]
    query: str,
    target_keys: list[str] | None = None,
    org_members: list[dict[str, Any]] | None = None,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch data from all relevant connectors in parallel.

    `history` is the prior conversation turns (role/content dicts). When the
    current message is a follow-up ("which is most urgent?") that contains no
    employee name or email, we scan history so the target user is still resolved.
    """
    target_user = extract_target_user(query, org_members, history=history)

    tasks = []
    for integration in connected_integrations:
        key = integration["connector_key"]
        if target_keys and key not in target_keys:
            continue
        credentials = dict(integration["credentials"])
        # Inject target_user for org-level connectors that query per-employee data
        if key in ("microsoft365", "onedrive", "teams") and target_user:
            credentials["target_user"] = target_user
        tasks.append(fetch_connector_data(key, credentials, query))
    if not tasks:
        return []
    return list(await asyncio.gather(*tasks))


def build_context_block(connector_results: list[dict[str, Any]]) -> str:
    """Render connector results as a context block for the LLM."""
    if not connector_results:
        return ""
    lines = ["<connector_data>"]
    for result in connector_results:
        key = result.get("connector", "unknown")
        if "error" in result:
            lines.append(f"[{key}] Error: {result['error']}")
            continue
        # Surface any informational message (e.g. "no target user specified")
        if "message" in result:
            lines.append(f"[{key}] Note: {result['message']}")
        items = result.get("results", [])
        target_user = result.get("target_user")
        source = result.get("source", key)
        if target_user:
            label = {"onedrive": "Files", "teams": "Meetings"}.get(source, "Emails")
            searched = result.get("searched_for", "")
            trivial = {"(latest emails)", "(recent files)", "(recent meetings)"}
            searched_str = f' (searched: "{searched}")' if searched and searched not in trivial else ""
            lines.append(f"[{key}] {label} for {target_user}{searched_str} — {len(items)} result(s):")
        else:
            lines.append(f"[{key}] {len(items)} result(s):")
        for item in items[:25]:
            lines.append(f"  - {json.dumps(item, default=str)[:2500]}")
    lines.append("</connector_data>")
    return "\n".join(lines)


async def stream_chat_response(
    messages: list[dict[str, str]],
    connector_results: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """
    Build the LLM prompt with connector context and stream the response.
    Yields text chunks as they arrive.
    """
    context = build_context_block(connector_results)
    system_messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if context:
        system_messages.append({"role": "system", "content": f"Here is relevant data from your connected tools:\n{context}"})

    full_messages = system_messages + messages

    response = await litellm.acompletion(
        model=settings.DEFAULT_LLM_MODEL,
        messages=full_messages,
        stream=True,
        api_key=settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
