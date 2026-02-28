"""Member (OrgEmployee) authentication router.

Provides login, org selection, profile, and password change endpoints
for employees whose login has been enabled by an org admin.
"""

from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentMember
from app.auth.member_auth import (
    create_member_token,
    create_selection_token,
    hash_password,
    verify_password,
    verify_selection_token,
)
from app.database import get_db
from app.models.organization import OrgEmployee, Organization
from app.schemas.member_auth import (
    MemberChangePasswordRequest,
    MemberLoginRequest,
    MemberLoginResponse,
    MemberMeResponse,
    MemberOrgInfo,
    MemberOrgSelectionRequired,
    MemberSelectOrgRequest,
)

router = APIRouter(prefix="/member-auth", tags=["member-auth"])


@router.post("/login")
async def member_login(
    body: MemberLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberLoginResponse | MemberOrgSelectionRequired:
    """Authenticate a member by email + password.

    If the email exists in multiple orgs with valid passwords, returns a
    selection token so the member can pick which org to log into.
    """
    email_lower = body.email.lower()

    result = await db.execute(
        select(OrgEmployee)
        .options(selectinload(OrgEmployee.organization))
        .where(
            OrgEmployee.work_email == email_lower,
            OrgEmployee.is_login_enabled == True,  # noqa: E712
        )
    )
    employees = result.scalars().all()

    # Check password against each matching employee record
    matched: list[OrgEmployee] = []
    for emp in employees:
        if emp.password_hash and verify_password(body.password, emp.password_hash):
            matched.append(emp)

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if len(matched) == 1:
        emp = matched[0]
        token = create_member_token(str(emp.id), str(emp.org_id), emp.work_email)
        return MemberLoginResponse(
            token=token,
            employee_id=emp.id,
            employee_name=emp.name,
            email=emp.work_email,
            org_id=emp.org_id,
            org_name=emp.organization.name,
        )

    # Multiple orgs — return selection token
    orgs = [
        MemberOrgInfo(
            org_id=emp.org_id,
            org_name=emp.organization.name,
            employee_id=emp.id,
            employee_name=emp.name,
        )
        for emp in matched
    ]
    selection_token = create_selection_token(
        email_lower, [str(emp.org_id) for emp in matched]
    )
    return MemberOrgSelectionRequired(
        selection_token=selection_token,
        orgs=orgs,
    )


@router.post("/select-org", response_model=MemberLoginResponse)
async def member_select_org(
    body: MemberSelectOrgRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberLoginResponse:
    """Complete login by selecting an org (multi-org scenario)."""
    try:
        payload = verify_selection_token(body.selection_token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired selection token: {exc}",
        ) from exc

    allowed_org_ids = payload.get("org_ids", [])
    if str(body.org_id) not in allowed_org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this organization",
        )

    email = payload.get("email", "")
    result = await db.execute(
        select(OrgEmployee)
        .options(selectinload(OrgEmployee.organization))
        .where(
            OrgEmployee.work_email == email,
            OrgEmployee.org_id == body.org_id,
            OrgEmployee.is_login_enabled == True,  # noqa: E712
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    token = create_member_token(str(emp.id), str(emp.org_id), emp.work_email)
    return MemberLoginResponse(
        token=token,
        employee_id=emp.id,
        employee_name=emp.name,
        email=emp.work_email,
        org_id=emp.org_id,
        org_name=emp.organization.name,
    )


@router.get("/me", response_model=MemberMeResponse)
async def member_me(
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberMeResponse:
    """Return the currently authenticated member's profile."""
    result = await db.execute(
        select(Organization).where(Organization.id == member.org_id)
    )
    org = result.scalar_one_or_none()
    return MemberMeResponse(
        employee_id=member.id,
        name=member.name,
        email=member.work_email,
        org_id=member.org_id,
        org_name=org.name if org else "Unknown",
        is_login_enabled=member.is_login_enabled,
    )


@router.patch("/change-password", response_model=MemberLoginResponse)
async def member_change_password(
    body: MemberChangePasswordRequest,
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberLoginResponse:
    """Allow a member to change their own password.

    Invalidates all other sessions and returns a fresh token.
    """
    if not member.password_hash or not verify_password(body.current_password, member.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    from datetime import datetime, timezone
    member.password_hash = hash_password(body.new_password)
    member.sessions_invalidated_at = datetime.now(timezone.utc)
    await db.flush()

    result = await db.execute(
        select(Organization).where(Organization.id == member.org_id)
    )
    org = result.scalar_one_or_none()

    token = create_member_token(str(member.id), str(member.org_id), member.work_email)
    return MemberLoginResponse(
        token=token,
        employee_id=member.id,
        employee_name=member.name,
        email=member.work_email,
        org_id=member.org_id,
        org_name=org.name if org else "Unknown",
    )
