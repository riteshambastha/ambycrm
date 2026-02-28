"""Custom JWT-based authentication for OrgEmployee (member) login.

This is a parallel auth system to the Clerk-based admin auth.  Members
log in with email + password (set by the org admin), and receive a JWT
signed with MEMBER_JWT_SECRET.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

_ALGORITHM = "HS256"


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_member_token(
    employee_id: str,
    org_id: str,
    email: str,
    *,
    expires_days: int | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": employee_id,
        "org_id": org_id,
        "email": email,
        "type": "member",
        "iat": now,
        "exp": now + timedelta(days=expires_days or settings.MEMBER_JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, settings.MEMBER_JWT_SECRET, algorithm=_ALGORITHM)


def create_selection_token(email: str, org_ids: list[str]) -> str:
    """Short-lived token used during org selection (multi-org login)."""
    now = datetime.now(timezone.utc)
    payload = {
        "email": email,
        "org_ids": org_ids,
        "type": "member_selection",
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.MEMBER_JWT_SECRET, algorithm=_ALGORITHM)


def verify_member_token(token: str) -> dict:
    """Decode and verify a member JWT.  Raises jwt.InvalidTokenError on failure."""
    payload = jwt.decode(token, settings.MEMBER_JWT_SECRET, algorithms=[_ALGORITHM])
    if payload.get("type") != "member":
        raise jwt.InvalidTokenError("Not a member token")
    return payload


def verify_selection_token(token: str) -> dict:
    """Decode and verify a member org-selection JWT."""
    payload = jwt.decode(token, settings.MEMBER_JWT_SECRET, algorithms=[_ALGORITHM])
    if payload.get("type") != "member_selection":
        raise jwt.InvalidTokenError("Not a selection token")
    return payload
