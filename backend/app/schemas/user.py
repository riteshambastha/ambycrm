import uuid
from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: uuid.UUID
    clerk_user_id: str
    email: str | None        # nullable — Clerk JWTs don't include email by default
    first_name: str | None
    last_name: str | None
    avatar_url: str | None
    is_super_admin: bool
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgMembershipOut(BaseModel):
    org_id: uuid.UUID
    org_name: str
    org_slug: str
    role: str
    plan: str
    max_seats: int

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
