import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccountContact(Base):
    """
    A contact from a Salesforce Account that people in the org are interacting with.
    Enriched with LinkedIn profile data via Apify.
    """

    __tablename__ = "account_contacts"
    __table_args__ = (
        UniqueConstraint("org_id", "salesforce_contact_id", name="uq_org_sf_contact"),
        Index("ix_account_contacts_org", "org_id"),
        Index("ix_account_contacts_email", "org_id", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    salesforce_contact_id: Mapped[str] = mapped_column(String(50), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    account_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_industry: Mapped[str | None] = mapped_column(String(255), nullable=True)

    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    salesforce_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    posts: Mapped[list["LinkedInPost"]] = relationship(
        "LinkedInPost", back_populates="contact", cascade="all, delete-orphan"
    )


class LinkedInPost(Base):
    """A single LinkedIn post belonging to an account contact."""

    __tablename__ = "linkedin_posts"
    __table_args__ = (
        Index("ix_linkedin_posts_contact", "contact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_contacts.id", ondelete="CASCADE"), nullable=False
    )
    post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    post_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contact: Mapped["AccountContact"] = relationship("AccountContact", back_populates="posts")
