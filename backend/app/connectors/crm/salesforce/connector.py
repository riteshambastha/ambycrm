"""
Salesforce CRM connector.

Supports both production (login.salesforce.com) and sandbox
(test.salesforce.com) via the SALESFORCE_LOGIN_DOMAIN env var.

OAuth flow:
  1. User clicks Connect → redirected to Salesforce login
  2. Salesforce redirects back with code + instance_url in the token response
  3. instance_url is stored in raw_data and used for all subsequent API calls

Queries Opportunities, Contacts, Accounts, and Leads via SOQL based on
the user's natural language prompt.
"""

import os
import re
from typing import Any

import httpx

from app.connectors.base import BaseConnector, ConnectorMetadata
from app.connectors.oauth_manager import build_authorization_url, compute_expires_at

_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
# "test.salesforce.com" for sandbox, "login.salesforce.com" for production
_LOGIN_DOMAIN = os.getenv("SALESFORCE_LOGIN_DOMAIN", "login.salesforce.com")
_AUTH_URL = f"https://{_LOGIN_DOMAIN}/services/oauth2/authorize"
_TOKEN_URL = f"https://{_LOGIN_DOMAIN}/services/oauth2/token"
_API_VERSION = "v59.0"

_INTENT = {
    "opportunity": ["deal", "deals", "opportunity", "opportunities", "pipeline", "stage", "close", "revenue", "amount"],
    "contact": ["contact", "contacts", "person", "email", "phone", "who"],
    "account": ["account", "accounts", "company", "companies", "customer", "client", "organization"],
    "lead": ["lead", "leads", "prospect", "prospects", "new lead"],
    "case": ["case", "cases", "support", "ticket", "issue"],
    "task": ["task", "tasks", "activity", "activities", "follow", "followup"],
}


def _detect_object(query: str) -> str:
    """Return the most relevant Salesforce object for the query."""
    lower = query.lower()
    scores: dict[str, int] = {obj: 0 for obj in _INTENT}
    for obj, keywords in _INTENT.items():
        for kw in keywords:
            if kw in lower:
                scores[obj] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "opportunity"


def _extract_keyword(query: str) -> str:
    """Pull a useful search term from the query (strip common navigation words)."""
    stop = {
        "show", "get", "find", "list", "fetch", "all", "my", "the", "for",
        "in", "of", "from", "about", "what", "are", "salesforce", "crm",
        "can", "you", "please", "open", "deal", "deals", "opportunity",
        "contact", "account", "lead", "latest", "recent",
    }
    parts = [w for w in re.sub(r"[^\w\s@.]", "", query).lower().split()
             if w not in stop and "@" not in w and len(w) > 2 and not w.isdigit()]
    return " ".join(parts[:3])


def _build_soql(obj: str, keyword: str, limit: int = 15) -> str:
    kw = keyword.replace("'", "\\'")

    if obj == "opportunity":
        where = f"Name LIKE '%{kw}%' OR Account.Name LIKE '%{kw}%'" if kw else "IsClosed = false"
        return (
            f"SELECT Id, Name, StageName, Amount, CloseDate, Probability, "
            f"Account.Name, OwnerId, Owner.Name "
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
        where = f"Name LIKE '%{kw}%' OR Company LIKE '%{kw}%' OR Email LIKE '%{kw}%'" if kw else "IsConverted = false"
        return (
            f"SELECT Id, Name, Company, Email, Phone, Status, LeadSource, Rating "
            f"FROM Lead WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )

    if obj == "case":
        where = f"Subject LIKE '%{kw}%' OR Description LIKE '%{kw}%'" if kw else "IsClosed = false"
        return (
            f"SELECT Id, CaseNumber, Subject, Status, Priority, Account.Name "
            f"FROM Case WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )

    if obj == "task":
        where = f"Subject LIKE '%{kw}%'" if kw else "IsClosed = false"
        return (
            f"SELECT Id, Subject, Status, Priority, ActivityDate, Who.Name, What.Name "
            f"FROM Task WHERE {where} "
            f"ORDER BY LastModifiedDate DESC LIMIT {limit}"
        )

    return f"SELECT Id, Name FROM {obj.capitalize()} LIMIT {limit}"


class SalesforceConnector(BaseConnector):
    metadata = ConnectorMetadata(
        key="salesforce",
        name="Salesforce",
        category="crm",
        auth_type="oauth2",
        scope="org",
        description="Connect your Salesforce CRM to query deals, contacts, accounts, leads, and more.",
        icon_url="/icons/salesforce.svg",
        oauth_scopes=["api", "refresh_token", "offline_access"],
        oauth_config={
            "auth_url": _AUTH_URL,
            "token_url": _TOKEN_URL,
        },
    )

    async def get_oauth_url(self, state: str, redirect_uri: str) -> str:
        return build_authorization_url(
            auth_url=_AUTH_URL,
            client_id=_CLIENT_ID,
            redirect_uri=redirect_uri,
            scopes=self.metadata.oauth_scopes,
            state=state,
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for tokens. Salesforce returns instance_url in the response."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            tokens = resp.json()

        tokens["expires_at"] = compute_expires_at(tokens.get("expires_in"))
        # instance_url comes directly from Salesforce — store it for later API calls
        return tokens

    async def refresh_token(self, credentials: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credentials["refresh_token"],
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            tokens = resp.json()

        tokens["expires_at"] = compute_expires_at(tokens.get("expires_in"))
        # Preserve existing instance_url if not returned again
        if "instance_url" not in tokens and "instance_url" in credentials:
            tokens["instance_url"] = credentials["instance_url"]
        return tokens

    async def test_connection(self, credentials: dict[str, Any]) -> bool:
        instance_url = credentials.get("instance_url") or os.getenv("SALESFORCE_INSTANCE_URL", "")
        if not instance_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{instance_url}/services/data/{_API_VERSION}/",
                    headers={"Authorization": f"Bearer {credentials['access_token']}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def fetch_data(self, credentials: dict[str, Any], query: str) -> dict[str, Any]:
        """Run an intent-aware SOQL query and return structured results."""
        instance_url = (
            credentials.get("instance_url")
            or os.getenv("SALESFORCE_INSTANCE_URL", "")
        )
        if not instance_url:
            return {"results": [], "source": "salesforce", "error": "No Salesforce instance URL configured."}

        access_token = credentials.get("access_token", "")

        # Parse a count from the query ("latest 10 deals" → 10)
        count_match = re.search(r"\b(\d+)\b", query)
        limit = min(int(count_match.group(1)), 50) if count_match else 15

        sf_object = _detect_object(query)
        keyword = _extract_keyword(query)
        soql = _build_soql(sf_object, keyword, limit=limit)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{instance_url}/services/data/{_API_VERSION}/query",
                params={"q": soql},
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code == 401:
            return {"results": [], "source": "salesforce", "error": "Auth failed — token may have expired. Please reconnect Salesforce."}
        if resp.status_code == 403:
            return {"results": [], "source": "salesforce", "error": "Permission denied. Check that the Connected App has the required API permissions."}
        if not resp.is_success:
            return {"results": [], "source": "salesforce", "error": f"Salesforce API error {resp.status_code}: {resp.text[:300]}"}

        data = resp.json()
        records = data.get("records", [])

        # Clean up internal Salesforce metadata fields from each record
        cleaned = []
        for rec in records:
            clean = {k: v for k, v in rec.items() if k not in ("attributes",) and not k.startswith("__")}
            # Flatten nested objects (e.g. Account.Name)
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
