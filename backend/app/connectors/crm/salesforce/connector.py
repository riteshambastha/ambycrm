"""
Salesforce CRM connector — Org-level client credentials flow.

No user OAuth redirect required. Uses the Connected App's Consumer Key +
Consumer Secret to get a bearer token directly from the instance's token
endpoint (same pattern as Microsoft 365 / OneDrive / Teams connectors).

Requires in .env:
  SALESFORCE_CLIENT_ID      — Consumer Key from the Connected App
  SALESFORCE_CLIENT_SECRET  — Consumer Secret from the Connected App
  SALESFORCE_INSTANCE_URL   — e.g. https://nailbiter--uat.sandbox.my.salesforce.com
  SALESFORCE_TOKEN_URL      — e.g. https://nailbiter--uat.sandbox.my.salesforce.com/services/oauth2/token

Queries Opportunities, Contacts, Accounts, Leads, Cases, and Tasks via
SOQL based on the user's natural language prompt.
"""

import os
import re
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata

_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL", "")
_TOKEN_URL = os.getenv(
    "SALESFORCE_TOKEN_URL",
    f"{_INSTANCE_URL}/services/oauth2/token" if _INSTANCE_URL else "",
)
_API_VERSION = "v62.0"

_INTENT = {
    "opportunity": ["deal", "deals", "opportunity", "opportunities", "pipeline", "stage", "close", "revenue", "amount", "won", "lost"],
    "contact": ["contact", "contacts", "person", "email", "phone", "who"],
    "account": ["account", "accounts", "company", "companies", "customer", "client", "organization"],
    "lead": ["lead", "leads", "prospect", "prospects"],
    "case": ["case", "cases", "support", "ticket", "issue"],
    "task": ["task", "tasks", "activity", "activities", "followup", "follow up"],
}


def _detect_object(query: str) -> str:
    lower = query.lower()
    scores: dict[str, int] = {obj: 0 for obj in _INTENT}
    for obj, keywords in _INTENT.items():
        for kw in keywords:
            if kw in lower:
                scores[obj] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "opportunity"


def _extract_keyword(query: str) -> str:
    stop = {
        "show", "get", "find", "list", "fetch", "all", "my", "the", "for",
        "in", "of", "from", "about", "what", "are", "salesforce", "crm",
        "can", "you", "please", "open", "deal", "deals", "opportunity",
        "opportunities", "contact", "contacts", "account", "accounts",
        "lead", "leads", "latest", "recent", "give",
    }
    parts = [
        w for w in re.sub(r"[^\w\s@.]", "", query).lower().split()
        if w not in stop and "@" not in w and len(w) > 2 and not w.isdigit()
    ]
    return " ".join(parts[:3])


def _build_soql(obj: str, keyword: str, limit: int = 15) -> str:
    kw = keyword.replace("'", "\\'")

    if obj == "opportunity":
        where = f"Name LIKE '%{kw}%' OR Account.Name LIKE '%{kw}%'" if kw else "IsClosed = false"
        return (
            f"SELECT Id, Name, StageName, Amount, CloseDate, Probability, "
            f"Account.Name, Owner.Name "
            f"FROM Opportunity WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
    if obj == "contact":
        where = (
            f"Name LIKE '%{kw}%' OR Email LIKE '%{kw}%' OR Account.Name LIKE '%{kw}%'"
            if kw else "Id != null"
        )
        return (
            f"SELECT Id, Name, Email, Phone, Title, Account.Name, LeadSource "
            f"FROM Contact WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
    if obj == "account":
        where = f"Name LIKE '%{kw}%' OR Industry LIKE '%{kw}%'" if kw else "Id != null"
        return (
            f"SELECT Id, Name, Industry, Phone, BillingCity, AnnualRevenue, "
            f"NumberOfEmployees, Type "
            f"FROM Account WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
    if obj == "lead":
        where = (
            f"Name LIKE '%{kw}%' OR Company LIKE '%{kw}%' OR Email LIKE '%{kw}%'"
            if kw else "IsConverted = false"
        )
        return (
            f"SELECT Id, Name, Company, Email, Phone, Status, LeadSource, Rating "
            f"FROM Lead WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
    if obj == "case":
        where = f"Subject LIKE '%{kw}%'" if kw else "IsClosed = false"
        return (
            f"SELECT Id, CaseNumber, Subject, Status, Priority, Account.Name "
            f"FROM Case WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
    if obj == "task":
        where = f"Subject LIKE '%{kw}%'" if kw else "IsClosed = false"
        return (
            f"SELECT Id, Subject, Status, Priority, ActivityDate "
            f"FROM Task WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )
    return f"SELECT Id, Name FROM {obj.capitalize()} LIMIT {limit}"


class SalesforceConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="salesforce",
        name="Salesforce",
        category="crm",
        auth_type="client_credentials",
        scope="org",
        description="Connect your Salesforce org to query deals, contacts, accounts, leads, and more via AI chat.",
        icon_url="/icons/salesforce.svg",
        oauth_scopes=[],
        oauth_config={},
    )

    # ------------------------------------------------------------------
    # Client credentials — no user redirect
    # ------------------------------------------------------------------

    async def get_org_token(self) -> dict[str, Any]:
        """Fetch a fresh access token using the client credentials flow."""
        if not _CLIENT_ID or not _CLIENT_SECRET or not _TOKEN_URL:
            raise RuntimeError(
                "SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET, and "
                "SALESFORCE_TOKEN_URL must be set in .env"
            )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "instance_url": data.get("instance_url", _INSTANCE_URL),
                "token_type": data.get("token_type", "Bearer"),
            }

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Salesforce uses client credentials — no OAuth redirect")

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError("Salesforce uses client credentials — no OAuth redirect")

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return await self.get_org_token()

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        try:
            fresh = await self.get_org_token()
            token = fresh["access_token"]
            instance_url = fresh.get("instance_url", _INSTANCE_URL)
        except Exception:
            return False
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{instance_url}/services/data/{_API_VERSION}/",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code == 200

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        try:
            fresh = await self.get_org_token()
            token = fresh["access_token"]
            instance_url = fresh.get("instance_url", _INSTANCE_URL)
        except Exception as exc:
            return {"results": [], "source": "salesforce", "error": f"Failed to get Salesforce token: {exc}"}

        # Parse explicit count ("show 10 deals" → LIMIT 10)
        count_match = re.search(r"\b(\d+)\b", query)
        limit = min(int(count_match.group(1)), 50) if count_match else 15

        sf_object = _detect_object(query)
        keyword = _extract_keyword(query)
        soql = _build_soql(sf_object, keyword, limit=limit)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{instance_url}/services/data/{_API_VERSION}/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code == 401:
            return {"results": [], "source": "salesforce", "error": "Auth failed — Salesforce token invalid."}
        if resp.status_code == 403:
            return {"results": [], "source": "salesforce", "error": "Permission denied. Check Connected App API permissions."}
        if not resp.is_success:
            return {"results": [], "source": "salesforce", "error": f"Salesforce API error {resp.status_code}: {resp.text[:300]}"}

        data = resp.json()
        records = data.get("records", [])

        # Strip Salesforce internal metadata from each record
        cleaned = []
        for rec in records:
            clean = {k: v for k, v in rec.items() if k != "attributes"}
            for k, v in list(clean.items()):
                if isinstance(v, dict) and "attributes" in v:
                    clean[k] = {ik: iv for ik, iv in v.items() if ik != "attributes"}
            cleaned.append(clean)

        return {
            "results": cleaned,
            "source": "salesforce",
            "object_type": sf_object,
            "total": data.get("totalSize", len(cleaned)),
            "searched_for": keyword or f"(recent {sf_object}s)",
        }
