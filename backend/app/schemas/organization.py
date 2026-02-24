import uuid
from datetime import datetime

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
    email: str
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    joined_at: datetime

    model_config = {"from_attributes": True}


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
