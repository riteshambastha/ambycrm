"""Pydantic schemas for member (OrgEmployee) authentication."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class MemberLoginRequest(BaseModel):
    email: EmailStr
    password: str


class MemberOrgInfo(BaseModel):
    org_id: uuid.UUID
    org_name: str
    employee_id: uuid.UUID
    employee_name: str


class MemberLoginResponse(BaseModel):
    token: str
    employee_id: uuid.UUID
    employee_name: str
    email: str
    org_id: uuid.UUID
    org_name: str


class MemberOrgSelectionRequired(BaseModel):
    requires_org_selection: bool = True
    selection_token: str
    orgs: list[MemberOrgInfo]


class MemberSelectOrgRequest(BaseModel):
    selection_token: str
    org_id: uuid.UUID


class MemberMeResponse(BaseModel):
    employee_id: uuid.UUID
    name: str
    email: str
    org_id: uuid.UUID
    org_name: str
    is_login_enabled: bool

    model_config = {"from_attributes": True}


class MemberChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
