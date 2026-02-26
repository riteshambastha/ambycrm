import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MemberProfileCache(Base):
    """
    Pre-cached connector data (emails, files, salesforce, meetings) for a
    specific person in an org, keyed by their work_email.

    Always caches up to 50 items. API endpoints slice to the requested limit,
    so changing limit from 10→20 never triggers a re-fetch.
    """

    __tablename__ = "member_profile_cache"
    __table_args__ = (
        UniqueConstraint("org_id", "work_email", "section", name="uq_member_cache"),
        Index("ix_member_cache_org_email", "org_id", "work_email"),
        Index("ix_member_cache_expires", "expires_at"),
        Index("ix_member_cache_last_viewed", "last_viewed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    work_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # "emails" | "files" | "salesforce" | "meetings"
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(100), nullable=False)
    # Raw connector results stored as JSONB — up to 50 items
    results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    # AI-generated actionable summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
