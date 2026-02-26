"""
Celery tasks for member profile data caching.

Tasks:
  - sync_member_section      — fetch one section for one person, store to cache
  - sync_member_all_sections — dispatch all 4 sections for one person in parallel
  - precache_org_members     — pre-warm caches for all org members with work_email
  - cleanup_expired_cache    — (Beat) delete TTL-expired + inactive cache rows
  - refresh_active_members_cache — (Beat) re-sync recently-viewed members
"""

import asyncio
import uuid
from typing import Any

import litellm

from app.celery_app import celery_app
from app.config import settings
from app.database import AsyncSessionLocal
from app.services.cache_service import (
    delete_expired_cache,
    delete_inactive_cache,
    get_active_member_emails,
    store_section_cache,
)
from app.services.integration_service import (
    SECTION_CONNECTOR_KEYS,
    load_connected_integrations,
)

# ── Pre-configured prompts per section ──────────────────────────────────────

_SECTION_QUERIES: dict[str, str] = {
    "emails": "Show the latest {limit} emails",
    "files": "Show the latest {limit} files",
    "salesforce": (
        "Show all data for {name} ({work_email})"
    ),
    "meetings": "Show the latest {limit} meeting recordings",
}

_SECTION_SYSTEM_PROMPTS: dict[str, str] = {
    "emails": (
        "You are summarizing someone's recent emails for a manager or colleague. "
        "Extract the most important themes in 3–5 bullet points: "
        "urgent items, pending action items, key senders, and important threads. "
        "Be concise, specific, and directly actionable. No preamble."
    ),
    "files": (
        "You are summarizing recently active files for a manager or colleague. "
        "Highlight in 3–4 bullet points: recently modified documents, what they likely "
        "contain based on their names, and any that may need attention. "
        "Be concise and actionable. No preamble."
    ),
    "salesforce": (
        "You are summarizing CRM data for a manager or colleague. "
        "In 4–5 bullet points summarize: pipeline health, overdue activities, "
        "key relationships, and anything time-sensitive. "
        "Flag risks and opportunities explicitly. No preamble."
    ),
    "meetings": (
        "You are summarizing recent meeting recordings for a manager or colleague. "
        "In 4–5 bullet points synthesize: recurring meeting themes, key decisions made, "
        "and open action items across all recordings. "
        "Be concise and actionable. No preamble."
    ),
}


async def _generate_summary(section: str, connector_results: list[dict[str, Any]]) -> str | None:
    """Generate a concise AI summary for a section's connector results."""
    if not connector_results:
        return None

    import json
    data_text = json.dumps(connector_results, default=str)[:8000]  # cap context size

    system_prompt = _SECTION_SYSTEM_PROMPTS.get(section, "Summarize this data concisely.")
    user_message = f"Here is the data:\n{data_text}\n\nProvide an actionable summary."

    try:
        response = await litellm.acompletion(
            model=settings.DEFAULT_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=400,
            api_key=settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY,
        )
        return response.choices[0].message.content or None
    except Exception:
        return None


async def _sync_section_async(
    org_id: uuid.UUID,
    work_email: str,
    person_name: str,
    section: str,
) -> None:
    """Async implementation of syncing one section for one person."""
    from app.services.ai_service import fetch_connector_data

    connector_keys = SECTION_CONNECTOR_KEYS.get(section, [])
    limit = settings.CACHE_MAX_ITEMS

    query = _SECTION_QUERIES[section].format(
        limit=limit,
        name=person_name,
        work_email=work_email,
    )

    async with AsyncSessionLocal() as db:
        connected = await load_connected_integrations(org_id, db)

        # Find active connectors for this section
        active = [i for i in connected if i["connector_key"] in connector_keys]
        if not active:
            return

        connector_key_used = active[0]["connector_key"]

        if section == "salesforce":
            from app.connectors.registry import registry
            sf_connector = registry.get_instance("salesforce")
            if sf_connector and hasattr(sf_connector, "fetch_person_overview"):
                sf_creds = next(
                    (dict(i["credentials"]) for i in active if i["connector_key"] == "salesforce"),
                    None,
                )
                if sf_creds:
                    result = await sf_connector.fetch_person_overview(
                        sf_creds, person_name, work_email, limit=limit,
                    )
                    all_results: list[dict[str, Any]] = result.get("results", [])
                    connector_key_used = "salesforce"
                else:
                    all_results = []
            else:
                all_results = []
        else:
            tasks = []
            for integration in active:
                creds = dict(integration["credentials"])
                if integration["connector_key"] in ("microsoft365", "onedrive", "teams"):
                    creds["target_user"] = work_email
                tasks.append(fetch_connector_data(integration["connector_key"], creds, query))

            results_list = await asyncio.gather(*tasks)

            all_results = []
            for r in results_list:
                if "error" not in r:
                    all_results.extend(r.get("results", []))
                    connector_key_used = r.get("connector", connector_key_used)

        summary = await _generate_summary(section, all_results)

        await store_section_cache(
            db=db,
            org_id=org_id,
            work_email=work_email,
            section=section,
            connector_key=connector_key_used,
            results=all_results,
            summary=summary,
        )
        await db.commit()


# ── Celery tasks ─────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.member_sync.sync_member_section", bind=True, max_retries=2)
def sync_member_section(
    self,
    org_id: str,
    work_email: str,
    person_name: str,
    section: str,
) -> None:
    """Fetch and cache one section for one person. Retries up to 2× on failure."""
    try:
        asyncio.run(
            _sync_section_async(
                org_id=uuid.UUID(org_id),
                work_email=work_email,
                person_name=person_name,
                section=section,
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.tasks.member_sync.sync_member_all_sections")
def sync_member_all_sections(
    org_id: str,
    work_email: str,
    person_name: str = "",
) -> None:
    """Dispatch all 4 section sync tasks for one person in parallel."""
    from celery import group

    job = group(
        sync_member_section.s(org_id, work_email, person_name, section)
        for section in ("emails", "files", "salesforce", "meetings")
    )
    job.apply_async()


async def _precache_org_members_async(org_id: uuid.UUID) -> None:
    """Load all members + employees with work_email and dispatch their sync jobs."""
    from sqlalchemy import select
    from app.models.organization import OrganizationMember, OrgEmployee
    from app.models.user import User
    from sqlalchemy.orm import selectinload

    async with AsyncSessionLocal() as db:
        # OrganizationMembers with work_email set
        member_result = await db.execute(
            select(OrganizationMember)
            .options(selectinload(OrganizationMember.user))
            .where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.work_email.isnot(None),
                OrganizationMember.is_active == True,  # noqa: E712
            )
        )
        for m in member_result.scalars().all():
            if m.work_email:
                name = f"{m.user.first_name or ''} {m.user.last_name or ''}".strip() or m.work_email
                sync_member_all_sections.delay(str(org_id), m.work_email, name)

        # OrgEmployees
        emp_result = await db.execute(
            select(OrgEmployee).where(OrgEmployee.org_id == org_id)
        )
        for e in emp_result.scalars().all():
            sync_member_all_sections.delay(str(org_id), e.work_email, e.name)


@celery_app.task(name="app.tasks.member_sync.precache_org_members")
def precache_org_members(org_id: str) -> None:
    """Pre-warm caches for all org members and employees with work_email set."""
    asyncio.run(_precache_org_members_async(uuid.UUID(org_id)))


async def _cleanup_async() -> None:
    async with AsyncSessionLocal() as db:
        expired = await delete_expired_cache(db)
        inactive = await delete_inactive_cache(db, inactive_days=30)
        await db.commit()
        if expired or inactive:
            import logging
            logging.getLogger("ambycrm").info(
                "Cache cleanup: deleted %d expired + %d inactive rows", expired, inactive
            )


@celery_app.task(name="app.tasks.member_sync.cleanup_expired_cache")
def cleanup_expired_cache() -> None:
    """Delete TTL-expired and long-inactive cache rows. Run by Celery Beat every hour."""
    asyncio.run(_cleanup_async())


async def _refresh_active_async() -> None:
    async with AsyncSessionLocal() as db:
        active = await get_active_member_emails(db, since_hours=24)
    for org_id, work_email in active:
        sync_member_all_sections.delay(str(org_id), work_email)


@celery_app.task(name="app.tasks.member_sync.refresh_active_members_cache")
def refresh_active_members_cache() -> None:
    """Re-sync caches for members viewed in the past 24 hours. Run by Beat every 4 hours."""
    asyncio.run(_refresh_active_async())
