from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.models.organization import Organization, OrganizationMember
from app.schemas.user import OrgMembershipOut, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/me/organizations", response_model=list[OrgMembershipOut])
async def my_organizations(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrgMembershipOut]:
    """Return all organizations the current user is an active member of."""
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.organization))
        .where(
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
    )
    memberships = result.scalars().all()
    return [
        OrgMembershipOut(
            org_id=m.org_id,
            org_name=m.organization.name,
            org_slug=m.organization.slug,
            role=m.role,
            plan=m.organization.plan,
            max_seats=m.organization.max_seats,
        )
        for m in memberships
    ]


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    if body.first_name is not None:
        current_user.first_name = body.first_name
    if body.last_name is not None:
        current_user.last_name = body.last_name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    await db.flush()
    return UserOut.model_validate(current_user)
