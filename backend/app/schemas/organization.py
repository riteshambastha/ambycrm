import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator


class OrganizationCreate(BaseModel):
    name: str
    slug: str

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v


class OrganizationUpdate(BaseModel):
    name: str | None = None
    settings: dict | None = None


class OrganizationOut(BaseModel):
    id: uuid.UUID
    clerk_org_id: str | None
    name: str
    slug: str
    plan: str
    max_seats: int
    is_active: bool
    settings: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str | None
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    work_email: str | None
    joined_at: datetime

    model_config = {"from_attributes": True}


class WorkEmailUpdate(BaseModel):
    work_email: str | None = None


class OrgEmployeeCreate(BaseModel):
    name: str
    work_email: EmailStr


class OrgEmployeeOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    work_email: str
    is_login_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class SetEmployeePasswordRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "user"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("user", "org_admin"):
            raise ValueError("Role must be 'user' or 'org_admin'")
        return v


class InvitationOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SectionResponse(BaseModel):
    """Response for a single member profile section (emails/files/salesforce/meetings)."""
    connected: bool
    results: list[dict[str, Any]]
    summary: str | None = None
    error: str | None = None
    limit: int
    # Cache metadata
    cached: bool = False
    fetched_at: datetime | None = None
    cache_status: str = "fresh"  # "fresh" | "stale_refresh" | "miss"


class PersonOut(BaseModel):
    """Unified person record for the Members list (member or employee)."""
    id: uuid.UUID
    person_type: str          # "member" | "employee"
    first_name: str | None
    last_name: str | None
    display_name: str
    email: str | None         # Clerk/login email
    work_email: str | None    # Microsoft 365 / connector email
    avatar_url: str | None
    role: str | None          # None for employees
    is_active: bool
    joined_at: datetime | None
