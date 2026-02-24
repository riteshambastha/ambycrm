"""
AI orchestration service.
Handles intent detection, parallel connector data fetching, and LLM streaming.
"""

import asyncio
import json
from typing import Any, AsyncIterator

import litellm

from app.config import settings
from app.connectors.registry import registry

# Which connector keys map to which intent keywords
_CONNECTOR_INTENT_MAP: dict[str, list[str]] = {
    "salesforce": ["salesforce", "deal", "opportunity", "crm", "pipeline", "account"],
    "hubspot": ["hubspot", "deal", "contact", "company"],
    "dynamics": ["dynamics", "microsoft crm"],
    "sugarcrm": ["sugarcrm", "sugar"],
    "google_workspace": ["gmail", "email", "google drive", "google docs", "drive"],
    "microsoft365": ["outlook", "onedrive", "office", "microsoft email"],
    "fireflies": ["fireflies", "meeting", "transcript", "recording", "call"],
    "teams": ["teams", "microsoft teams", "meeting"],
    "otter": ["otter", "transcript"],
    "recall": ["recall", "recording"],
}

_SYSTEM_PROMPT = """You are AmbyChat, an AI assistant that has access to enterprise tools like CRMs, email, documents, and meeting transcripts.

When answering, you have been provided with relevant data fetched from connected integrations.
Always:
- Cite the source of data (e.g., "From Salesforce:", "From Fireflies transcript:").
- Be concise and structured.
- If data is missing or unavailable, say so clearly.
"""


def detect_connectors(message: str) -> list[str]:
    """Heuristically detect which connectors are relevant to the message."""
    lower = message.lower()
    matched = []
    for key, keywords in _CONNECTOR_INTENT_MAP.items():
        if any(kw in lower for kw in keywords):
            matched.append(key)
    # If no match, try all connected connectors (caller filters by what's actually connected)
    return matched


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
) -> list[dict[str, Any]]:
    """Fetch data from all relevant connectors in parallel."""
    tasks = []
    for integration in connected_integrations:
        key = integration["connector_key"]
        if target_keys and key not in target_keys:
            continue
        tasks.append(
            fetch_connector_data(key, integration["credentials"], query)
        )
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
        items = result.get("results", [])
        lines.append(f"[{key}] {len(items)} result(s):")
        for item in items[:5]:
            lines.append(f"  - {json.dumps(item, default=str)[:300]}")
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
