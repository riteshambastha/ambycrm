"""FastAPI dependency injection for auth and RBAC."""

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.clerk import verify_clerk_token
from app.auth.member_auth import verify_member_token
from app.database import get_db
from app.models.organization import Organization, OrgEmployee, OrganizationMember
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Verify the Clerk JWT and return (or upsert) the local User record."""
    token = credentials.credentials
    try:
        payload = await verify_clerk_token(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    clerk_user_id: str = payload.get("sub", "")
    if not clerk_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject in token")

    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()

    if user is None:
        # First-time login: extract what we can from the JWT payload.
        # Clerk JWTs include email only when a custom template adds it; fall back to None.
        email: str | None = payload.get("email") or None
        if not email and isinstance(payload.get("email_addresses"), list):
            first = (payload["email_addresses"] or [{}])[0]
            email = first.get("email_address") or None

        user = User(
            clerk_user_id=clerk_user_id,
            email=email,
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
        )
        db.add(user)
        await db.flush()

    # Update last_seen_at
    user.last_seen_at = datetime.now(timezone.utc)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_org_membership(
    org_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationMember:
    """Verify the user is an active member of the requested org."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")
    return membership


async def require_org_admin(
    org_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationMember:
    """Verify the user is an org_admin or super_admin."""
    membership = await get_current_org_membership(org_id, current_user, db)
    if membership.role not in ("org_admin",) and not current_user.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin access required")
    return membership


async def require_super_admin(current_user: CurrentUser) -> User:
    if not current_user.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user


SuperAdmin = Annotated[User, Depends(require_super_admin)]


# ── Member (OrgEmployee) auth ─────────────────────────────────────────────────

async def get_current_member(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgEmployee:
    """Verify a member JWT and return the OrgEmployee record.

    Checks:
    - Token is valid and of type 'member'
    - Employee exists and has login enabled
    - Token was issued after the last session invalidation
    """
    token = credentials.credentials
    try:
        payload = verify_member_token(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    employee_id = payload.get("sub")
    if not employee_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject in token")

    result = await db.execute(select(OrgEmployee).where(OrgEmployee.id == employee_id))
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    if not employee.is_login_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login disabled for this account")

    # Check session invalidation — reject tokens issued before invalidation timestamp
    if employee.sessions_invalidated_at:
        token_iat = payload.get("iat")
        if token_iat and datetime.fromtimestamp(token_iat, tz=timezone.utc) < employee.sessions_invalidated_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been invalidated. Please log in again.",
            )

    return employee


CurrentMember = Annotated[OrgEmployee, Depends(get_current_member)]
