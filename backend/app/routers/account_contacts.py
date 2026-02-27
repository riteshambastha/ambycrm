"""Account Contacts router — Salesforce contact sync + LinkedIn enrichment."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_org_membership
from app.database import get_db
from app.models.account_contact import AccountContact, LinkedInPost
from app.schemas.account_contact import AccountContactOut, LinkedInPostOut, SyncSummaryOut
from app.services import contact_sync_service

router = APIRouter(
    prefix="/organizations/{org_id}/account-contacts",
    tags=["account-contacts"],
)


@router.get("", response_model=list[AccountContactOut])
async def list_account_contacts(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AccountContactOut]:
    """List all account contacts for the org with their LinkedIn post counts."""
    await get_current_org_membership(str(org_id), current_user, db)

    post_count_sub = (
        select(
            LinkedInPost.contact_id,
            func.count(LinkedInPost.id).label("post_count"),
        )
        .group_by(LinkedInPost.contact_id)
        .subquery()
    )

    result = await db.execute(
        select(AccountContact, func.coalesce(post_count_sub.c.post_count, 0).label("post_count"))
        .outerjoin(post_count_sub, AccountContact.id == post_count_sub.c.contact_id)
        .where(AccountContact.org_id == org_id)
        .order_by(AccountContact.name)
    )

    contacts = []
    for row in result.all():
        contact = row[0]
        out = AccountContactOut.model_validate(contact)
        out.post_count = row[1]
        contacts.append(out)

    return contacts


@router.post("/refresh", response_model=SyncSummaryOut)
async def refresh_account_contacts(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SyncSummaryOut:
    """
    Trigger a full sync: fetch contacts from Salesforce, resolve LinkedIn
    profiles for new contacts, and fetch recent posts.
    """
    await get_current_org_membership(str(org_id), current_user, db)
    summary = await contact_sync_service.sync_account_contacts(org_id)
    return SyncSummaryOut(**summary)


@router.get("/{contact_id}/posts", response_model=list[LinkedInPostOut])
async def list_contact_posts(
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LinkedInPostOut]:
    """List LinkedIn posts for a specific account contact."""
    await get_current_org_membership(str(org_id), current_user, db)

    contact_result = await db.execute(
        select(AccountContact).where(
            AccountContact.id == contact_id,
            AccountContact.org_id == org_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    posts_result = await db.execute(
        select(LinkedInPost)
        .where(LinkedInPost.contact_id == contact_id)
        .order_by(LinkedInPost.posted_at.desc().nulls_last())
    )
    return [LinkedInPostOut.model_validate(p) for p in posts_result.scalars().all()]


@router.post("/{contact_id}/posts/refresh", response_model=list[LinkedInPostOut])
async def refresh_contact_posts(
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LinkedInPostOut]:
    """Fetch latest LinkedIn posts for a single contact on demand."""
    await get_current_org_membership(str(org_id), current_user, db)

    contact_result = await db.execute(
        select(AccountContact).where(
            AccountContact.id == contact_id,
            AccountContact.org_id == org_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if not contact.linkedin_url:
        raise HTTPException(status_code=400, detail="Contact has no LinkedIn profile")

    from app.services import linkedin_service
    from app.services.contact_sync_service import _save_posts

    posts = await linkedin_service.fetch_recent_posts(contact.linkedin_url, count=10)
    if posts:
        await _save_posts(contact.id, posts)

    posts_result = await db.execute(
        select(LinkedInPost)
        .where(LinkedInPost.contact_id == contact_id)
        .order_by(LinkedInPost.posted_at.desc().nulls_last())
    )
    return [LinkedInPostOut.model_validate(p) for p in posts_result.scalars().all()]
