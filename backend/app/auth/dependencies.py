"""FastAPI dependency injection for auth and RBAC."""

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.clerk import verify_clerk_token
from app.database import get_db
from app.models.organization import Organization, OrganizationMember
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Verify the Clerk JWT and return (or upsert) the local User record."""
    token = credentials.credentials
    try:
        payload = verify_clerk_token(token)
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
        # First-time login: create shadow user record
        email = (payload.get("email_addresses") or [{}])[0].get("email_address", "") if isinstance(
            payload.get("email_addresses"), list
        ) else payload.get("email", "")
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
