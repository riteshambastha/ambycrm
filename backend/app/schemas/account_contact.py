import uuid
from datetime import datetime

from pydantic import BaseModel


class AccountContactOut(BaseModel):
    id: uuid.UUID
    salesforce_contact_id: str
    name: str
    email: str | None
    title: str | None
    phone: str | None
    account_id: str | None
    account_name: str | None
    account_industry: str | None
    linkedin_url: str | None
    linkedin_fetched_at: datetime | None
    post_count: int = 0
    salesforce_synced_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkedInPostOut(BaseModel):
    id: uuid.UUID
    post_url: str | None
    post_text: str | None
    posted_at: datetime | None
    fetched_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncSummaryOut(BaseModel):
    contacts_synced: int
    linkedin_profiles_found: int
    posts_fetched: int
