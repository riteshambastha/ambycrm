"""
Account Contact Sync Service.

Orchestrates:
1. Fetching contacts from Salesforce (those belonging to an Account)
2. Upserting them into the local account_contacts table
3. Resolving LinkedIn profiles via Apify (name + company lookup)
4. Fetching recent LinkedIn posts and storing them

Uses short-lived DB sessions for each write batch to avoid holding
connections during slow external API calls.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors.crm.salesforce.connector import SalesforceConnector
from app.database import AsyncSessionLocal
from app.models.account_contact import AccountContact, LinkedInPost
from app.services import linkedin_service

logger = logging.getLogger(__name__)

POSTS_STALE_HOURS = 24


def _extract_nested(record: dict, parent_key: str, child_key: str) -> str | None:
    """Safely extract a nested Salesforce relationship field like Account.Name."""
    parent = record.get(parent_key)
    if isinstance(parent, dict):
        return parent.get(child_key)
    return None


async def _fetch_salesforce_contacts() -> list[dict[str, Any]]:
    """Call Salesforce to get all contacts that belong to an Account."""
    connector = SalesforceConnector()
    result = await connector.fetch_account_contacts(limit=500)
    if "error" in result:
        logger.error("Salesforce contact fetch failed: %s", result["error"])
        return []
    return result.get("records", [])


async def _upsert_contacts(
    org_id: uuid.UUID,
    sf_records: list[dict[str, Any]],
) -> int:
    """Upsert Salesforce contacts into account_contacts, return count upserted."""
    if not sf_records:
        return 0

    now = datetime.now(timezone.utc)
    rows = []
    for rec in sf_records:
        sf_id = rec.get("Id")
        if not sf_id:
            continue
        rows.append({
            "id": uuid.uuid4(),
            "org_id": org_id,
            "salesforce_contact_id": sf_id,
            "name": rec.get("Name", ""),
            "email": rec.get("Email"),
            "title": rec.get("Title"),
            "phone": rec.get("Phone"),
            "account_id": _extract_nested(rec, "Account", "Id"),
            "account_name": _extract_nested(rec, "Account", "Name"),
            "account_industry": _extract_nested(rec, "Account", "Industry"),
            "salesforce_synced_at": now,
        })

    if not rows:
        return 0

    stmt = pg_insert(AccountContact).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_org_sf_contact",
        set_={
            "name": stmt.excluded.name,
            "email": stmt.excluded.email,
            "title": stmt.excluded.title,
            "phone": stmt.excluded.phone,
            "account_id": stmt.excluded.account_id,
            "account_name": stmt.excluded.account_name,
            "account_industry": stmt.excluded.account_industry,
            "salesforce_synced_at": stmt.excluded.salesforce_synced_at,
            "updated_at": now,
        },
    )
    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()
    return len(rows)


@dataclass
class _ContactStub:
    id: uuid.UUID
    email: str | None
    name: str
    account_name: str | None
    linkedin_url: str | None


async def _get_contacts_needing_linkedin(org_id: uuid.UUID) -> list[_ContactStub]:
    """Load contacts that haven't had a LinkedIn lookup attempt yet."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                AccountContact.id,
                AccountContact.email,
                AccountContact.name,
                AccountContact.account_name,
                AccountContact.linkedin_url,
            ).where(
                AccountContact.org_id == org_id,
                AccountContact.linkedin_fetched_at.is_(None),
            )
        )
        return [
            _ContactStub(
                id=r.id,
                email=r.email,
                name=r.name,
                account_name=r.account_name,
                linkedin_url=r.linkedin_url,
            )
            for r in result.all()
        ]


async def _save_linkedin_result(contact_id: uuid.UUID, url: str | None) -> None:
    """Persist a single LinkedIn lookup result."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            AccountContact.__table__.update()
            .where(AccountContact.id == contact_id)
            .values(
                linkedin_url=url,
                linkedin_fetched_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def _enrich_linkedin_profiles(org_id: uuid.UUID) -> int:
    """
    For contacts without a linkedin_url (never attempted), resolve via Apify.
    Uses name + company for the lookup.
    External HTTP calls happen outside any DB session.
    """
    contacts = await _get_contacts_needing_linkedin(org_id)
    found = 0

    for contact in contacts:
        url = await linkedin_service.find_linkedin_profile(
            contact.name, contact.account_name
        )
        await _save_linkedin_result(contact.id, url)
        if url:
            found += 1

    return found


@dataclass
class _PostCandidate:
    contact_id: uuid.UUID
    linkedin_url: str
    needs_refresh: bool


async def _get_contacts_needing_posts(org_id: uuid.UUID) -> list[_PostCandidate]:
    """Find contacts with a linkedin_url whose posts are stale or missing."""
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=POSTS_STALE_HOURS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AccountContact.id, AccountContact.linkedin_url).where(
                AccountContact.org_id == org_id,
                AccountContact.linkedin_url.isnot(None),
            )
        )
        rows = result.all()

        candidates: list[_PostCandidate] = []
        for r in rows:
            latest = await db.execute(
                select(LinkedInPost.fetched_at)
                .where(LinkedInPost.contact_id == r.id)
                .order_by(LinkedInPost.fetched_at.desc())
                .limit(1)
            )
            last_fetched = latest.scalar_one_or_none()
            needs = not last_fetched or last_fetched <= stale_cutoff
            if needs:
                candidates.append(_PostCandidate(
                    contact_id=r.id,
                    linkedin_url=r.linkedin_url,
                    needs_refresh=True,
                ))
        return candidates


async def _save_posts(contact_id: uuid.UUID, posts: list[dict[str, Any]]) -> None:
    """Replace stored posts for one contact."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(LinkedInPost).where(LinkedInPost.contact_id == contact_id)
        )
        for p in posts:
            db.add(LinkedInPost(
                contact_id=contact_id,
                post_url=p.get("post_url"),
                post_text=p.get("text"),
                posted_at=p.get("posted_at"),
                fetched_at=datetime.now(timezone.utc),
            ))
        await db.commit()


async def _fetch_and_store_posts(org_id: uuid.UUID) -> int:
    """
    For contacts with a linkedin_url whose posts are missing or stale,
    fetch 10 recent posts and store them.
    External HTTP calls happen outside any DB session.
    """
    candidates = await _get_contacts_needing_posts(org_id)
    total_posts = 0

    for c in candidates:
        posts = await linkedin_service.fetch_recent_posts(c.linkedin_url, count=10)
        if not posts:
            continue
        await _save_posts(c.contact_id, posts)
        total_posts += len(posts)

    return total_posts


async def sync_account_contacts(
    org_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Full sync pipeline:
    1. Fetch contacts from Salesforce (external HTTP, no DB)
    2. Upsert into account_contacts (short DB session)
    3. Resolve LinkedIn profiles for new contacts (HTTP + short DB writes)
    4. Fetch LinkedIn posts for enriched contacts (HTTP + short DB writes)

    Returns a summary dict.
    """
    sf_records = await _fetch_salesforce_contacts()
    synced = await _upsert_contacts(org_id, sf_records)

    api_up = await linkedin_service.is_api_available()
    linkedin_found = 0
    posts_fetched = 0
    if api_up:
        linkedin_found = await _enrich_linkedin_profiles(org_id)
        posts_fetched = await _fetch_and_store_posts(org_id)
    else:
        logger.info("Apify API unavailable — skipping LinkedIn enrichment for org %s", org_id)

    summary = {
        "contacts_synced": synced,
        "linkedin_profiles_found": linkedin_found,
        "posts_fetched": posts_fetched,
    }
    logger.info("Account contact sync complete for org %s: %s", org_id, summary)
    return summary
