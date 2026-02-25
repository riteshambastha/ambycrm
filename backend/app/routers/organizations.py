import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_org_membership, require_org_admin
from app.database import get_db
from app.models.organization import Invitation, OrgEmployee, Organization, OrganizationMember
from app.models.user import User
from app.schemas.organization import (
    InvitationOut,
    InviteCreate,
    MemberOut,
    OrgEmployeeCreate,
    OrgEmployeeOut,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    WorkEmailUpdate,
)
from app.services.email_service import send_invitation_email
from app.config import settings

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationOut:
    """Create a new organization. The creator becomes org_admin."""
    existing = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already taken")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        org_id=org.id,
        user_id=current_user.id,
        role="org_admin",
        invited_by=current_user.id,
    )
    db.add(member)
    await db.flush()
    return OrganizationOut.model_validate(org)


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationOut:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationOut.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationOut:
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if body.name is not None:
        org.name = body.name
    if body.settings is not None:
        org.settings = body.settings
    await db.flush()
    return OrganizationOut.model_validate(org)


# ── Members ───────────────────────────────────────────────────────────────────

@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[MemberOut]:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.org_id == org_id)
    )
    members = result.scalars().all()
    return [
        MemberOut(
            id=m.id,
            user_id=m.user_id,
            email=m.user.email,
            first_name=m.user.first_name,
            last_name=m.user.last_name,
            avatar_url=m.user.avatar_url,
            role=m.role,
            is_active=m.is_active,
            work_email=m.work_email,
            joined_at=m.joined_at,
        )
        for m in members
    ]


@router.patch("/{org_id}/members/{member_id}/deactivate", response_model=MemberOut)
async def deactivate_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberOut:
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.id == member_id, OrganizationMember.org_id == org_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    member.is_active = False
    await db.flush()
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        first_name=member.user.first_name,
        last_name=member.user.last_name,
        avatar_url=member.user.avatar_url,
        role=member.role,
        is_active=member.is_active,
        work_email=member.work_email,
        joined_at=member.joined_at,
    )


@router.patch("/{org_id}/members/{member_id}/role")
async def update_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    role: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    await require_org_admin(str(org_id), current_user, db)
    if role not in ("user", "org_admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id, OrganizationMember.org_id == org_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = role
    await db.flush()
    return {"id": str(member.id), "role": member.role}


@router.patch("/{org_id}/members/{member_id}/work-email", response_model=MemberOut)
async def set_member_work_email(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    body: WorkEmailUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberOut:
    """Set or update the Microsoft 365 work email for an org member."""
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.id == member_id, OrganizationMember.org_id == org_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.work_email = body.work_email
    await db.flush()
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        first_name=member.user.first_name,
        last_name=member.user.last_name,
        avatar_url=member.user.avatar_url,
        role=member.role,
        is_active=member.is_active,
        work_email=member.work_email,
        joined_at=member.joined_at,
    )


# ── Invitations ───────────────────────────────────────────────────────────────

@router.post("/{org_id}/invitations", response_model=InvitationOut, status_code=201)
async def invite_user(
    org_id: uuid.UUID,
    body: InviteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationOut:
    await require_org_admin(str(org_id), current_user, db)

    # Check seat limit
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    active_count_result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.is_active == True  # noqa: E712
        )
    )
    active_members = active_count_result.scalars().all()
    if len(active_members) >= org.max_seats:
        raise HTTPException(status_code=400, detail=f"Seat limit reached ({org.max_seats} seats)")

    token = secrets.token_urlsafe(32)
    invite = Invitation(
        org_id=org_id,
        email=body.email,
        role=body.role,
        invited_by=current_user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.flush()

    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={token}"
    await send_invitation_email(
        to_email=body.email,
        org_name=org.name,
        inviter_name=current_user.full_name,
        invite_url=invite_url,
    )

    return InvitationOut.model_validate(invite)


@router.post("/accept-invitation")
async def accept_invitation(
    token: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(
        select(Invitation).where(Invitation.token == token, Invitation.accepted_at == None)  # noqa: E711
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found or already accepted")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")

    member = OrganizationMember(
        org_id=invite.org_id,
        user_id=current_user.id,
        role=invite.role,
        invited_by=invite.invited_by,
        # Pre-populate work_email from the invitation email (the org/work address)
        work_email=invite.email,
    )
    db.add(member)
    invite.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    return {"org_id": str(invite.org_id), "role": invite.role}


# ── Org Employees (M365 mailbox targets) ─────────────────────────────────────

@router.get("/{org_id}/employees", response_model=list[OrgEmployeeOut])
async def list_employees(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrgEmployeeOut]:
    """List all employees registered for Microsoft 365 email queries."""
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(OrgEmployee)
        .where(OrgEmployee.org_id == org_id)
        .order_by(OrgEmployee.name)
    )
    return [OrgEmployeeOut.model_validate(e) for e in result.scalars().all()]


@router.post("/{org_id}/employees", response_model=OrgEmployeeOut, status_code=status.HTTP_201_CREATED)
async def add_employee(
    org_id: uuid.UUID,
    body: OrgEmployeeCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgEmployeeOut:
    """Add an employee for Microsoft 365 email querying (no AmbyChat account required)."""
    await require_org_admin(str(org_id), current_user, db)
    employee = OrgEmployee(
        org_id=org_id,
        name=body.name,
        work_email=str(body.work_email).lower(),
    )
    db.add(employee)
    await db.flush()
    return OrgEmployeeOut.model_validate(employee)


@router.delete("/{org_id}/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee(
    org_id: uuid.UUID,
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove an employee record."""
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(OrgEmployee).where(OrgEmployee.id == employee_id, OrgEmployee.org_id == org_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.delete(employee)
    await db.flush()
