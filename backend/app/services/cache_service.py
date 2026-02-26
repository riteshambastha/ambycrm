"""
Member profile cache service.
Handles read, write, and invalidation of MemberProfileCache rows.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.member_cache import MemberProfileCache
from app.schemas.organization import SectionResponse

# TTL seconds per section type
_SECTION_TTL: dict[str, int] = {
    "emails": settings.CACHE_TTL_EMAILS,
    "files": settings.CACHE_TTL_FILES,
    "salesforce": settings.CACHE_TTL_SALESFORCE,
    "meetings": settings.CACHE_TTL_MEETINGS,
}

# Background refresh is triggered when < this many seconds remain until expiry
_STALE_THRESHOLD_SECONDS = 30 * 60  # 30 minutes


def _ttl_for(section: str) -> int:
    return _SECTION_TTL.get(section, 3600)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_section_cache(
    db: AsyncSession,
    org_id: uuid.UUID,
    work_email: str,
    section: str,
    limit: int,
) -> tuple[SectionResponse | None, bool]:
    """
    Fetch a cached section result.
    Returns (SectionResponse, is_stale).
    Returns (None, False) on cache miss.
    """
    result = await db.execute(
        select(MemberProfileCache).where(
            MemberProfileCache.org_id == org_id,
            MemberProfileCache.work_email == work_email.lower(),
            MemberProfileCache.section == section,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None, False

    now = _now()
    is_expired = entry.expires_at.replace(tzinfo=timezone.utc) < now
    is_stale = (
        not is_expired
        and (entry.expires_at.replace(tzinfo=timezone.utc) - now).total_seconds()
        < _STALE_THRESHOLD_SECONDS
    )

    # Update last_viewed_at asynchronously (fire and forget within the same session)
    await db.execute(
        update(MemberProfileCache)
        .where(MemberProfileCache.id == entry.id)
        .values(last_viewed_at=now)
    )

    raw_results: list[dict[str, Any]] = entry.results if isinstance(entry.results, list) else []
    sliced = raw_results[:limit]

    fetched_at = entry.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)

    response = SectionResponse(
        connected=True,
        results=sliced,
        summary=entry.summary,
        limit=limit,
        cached=True,
        fetched_at=fetched_at,
        cache_status="stale_refresh" if (is_stale or is_expired) else "fresh",
    )
    return response, is_stale or is_expired


async def store_section_cache(
    db: AsyncSession,
    org_id: uuid.UUID,
    work_email: str,
    section: str,
    connector_key: str,
    results: list[dict[str, Any]],
    summary: str | None,
) -> None:
    """Upsert a cache entry (insert or replace on unique constraint)."""
    now = _now()
    ttl_seconds = _ttl_for(section)
    expires_at = now + timedelta(seconds=ttl_seconds)

    # Trim to max cache size
    trimmed = results[: settings.CACHE_MAX_ITEMS]

    stmt = (
        pg_insert(MemberProfileCache)
        .values(
            id=uuid.uuid4(),
            org_id=org_id,
            work_email=work_email.lower(),
            section=section,
            connector_key=connector_key,
            results=trimmed,
            summary=summary,
            item_count=len(trimmed),
            fetched_at=now,
            expires_at=expires_at,
            last_viewed_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_member_cache",
            set_={
                "connector_key": connector_key,
                "results": trimmed,
                "summary": summary,
                "item_count": len(trimmed),
                "fetched_at": now,
                "expires_at": expires_at,
                "last_viewed_at": now,
            },
        )
    )
    await db.execute(stmt)


async def invalidate_member_cache(
    db: AsyncSession,
    org_id: uuid.UUID,
    work_email: str,
) -> None:
    """Delete all cached sections for a specific person."""
    await db.execute(
        delete(MemberProfileCache).where(
            MemberProfileCache.org_id == org_id,
            MemberProfileCache.work_email == work_email.lower(),
        )
    )


async def invalidate_section_cache(
    db: AsyncSession,
    org_id: uuid.UUID,
    work_email: str,
    section: str,
) -> None:
    """Delete one cached section for a specific person."""
    await db.execute(
        delete(MemberProfileCache).where(
            MemberProfileCache.org_id == org_id,
            MemberProfileCache.work_email == work_email.lower(),
            MemberProfileCache.section == section,
        )
    )


async def delete_expired_cache(db: AsyncSession) -> int:
    """Delete all cache entries past their TTL. Returns count deleted."""
    now = _now()
    result = await db.execute(
        delete(MemberProfileCache).where(MemberProfileCache.expires_at < now)
    )
    return result.rowcount  # type: ignore[return-value]


async def delete_inactive_cache(db: AsyncSession, inactive_days: int = 30) -> int:
    """Delete cache for members not viewed in `inactive_days` days."""
    cutoff = _now() - timedelta(days=inactive_days)
    result = await db.execute(
        delete(MemberProfileCache).where(MemberProfileCache.last_viewed_at < cutoff)
    )
    return result.rowcount  # type: ignore[return-value]


async def get_active_member_emails(
    db: AsyncSession,
    since_hours: int = 24,
) -> list[tuple[uuid.UUID, str]]:
    """
    Return (org_id, work_email) pairs for members viewed recently.
    Used by Celery Beat to decide which members to pre-refresh.
    """
    cutoff = _now() - timedelta(hours=since_hours)
    result = await db.execute(
        select(MemberProfileCache.org_id, MemberProfileCache.work_email)
        .where(MemberProfileCache.last_viewed_at >= cutoff)
        .distinct()
    )
    return list(result.all())
