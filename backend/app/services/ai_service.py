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
        "outlook", "onedrive", "office 365",
        "email", "emails", "inbox", "mail", "message",  # generic email terms
        "microsoft email", "microsoft mail",
    ],
    "fireflies": ["fireflies", "transcript", "recording", "call summary"],
    "teams": ["teams", "microsoft teams"],
    "otter": ["otter", "otter.ai"],
    "recall": ["recall", "recall.ai"],
    # Generic terms that could apply to any meeting connector
    "meeting": ["meeting", "meetings", "summary", "summarize my meeting"],
}

_SYSTEM_PROMPT = """You are AmbyChat, an AI assistant that has access to enterprise tools like CRMs, email, documents, and meeting transcripts.

When answering, you have been provided with relevant data fetched from connected integrations.
Always:
- Cite the source of data (e.g., "From Salesforce:", "From Fireflies transcript:").
- Be concise and structured.
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


def extract_target_user(
    message: str,
    org_members: list[dict[str, Any]] | None = None,
) -> str | None:
    """
    Extract a target user email from the natural-language message.

    Priority:
    1. An explicit email address anywhere in the message.
    2. A member's full name that matches text in the message (uses work_email).

    Examples:
      "Show emails for john@acme.com"    → "john@acme.com"
      "What did Sarah Johnson receive?"  → "sarah.johnson@acme.com"  (if in org_members)
    """
    # 1. Direct email address in message
    email_match = re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", message)
    if email_match:
        return email_match.group(0).lower()

    # 2. Match a member's name against the message
    if org_members:
        lower = message.lower()
        for member in org_members:
            work_email = member.get("work_email")
            if not work_email:
                continue
            first = (member.get("first_name") or "").strip().lower()
            last = (member.get("last_name") or "").strip().lower()
            full = f"{first} {last}".strip()
            if full and full in lower:
                return work_email
            # Try first name alone only if it is longer than 3 chars (avoid false positives)
            if first and len(first) > 3 and first in lower:
                return work_email
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
) -> list[dict[str, Any]]:
    """Fetch data from all relevant connectors in parallel."""
    # Pre-compute target user for Microsoft365 org-level connector
    target_user = extract_target_user(query, org_members)

    tasks = []
    for integration in connected_integrations:
        key = integration["connector_key"]
        if target_keys and key not in target_keys:
            continue
        credentials = dict(integration["credentials"])
        # Inject target_user so the Microsoft365 connector knows whose mailbox to query
        if key == "microsoft365" and target_user:
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
        if result.get("target_user"):
            lines.append(f"[{key}] Emails for {result['target_user']} — {len(items)} result(s):")
        else:
            lines.append(f"[{key}] {len(items)} result(s):")
        for item in items[:10]:
            lines.append(f"  - {json.dumps(item, default=str)[:400]}")
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
