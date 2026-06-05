import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="free")

    # LLM — set by staff only, encrypted at rest
    llm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Billing placeholders (Stripe wired later)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(50), nullable=False, default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="organization")
    data_sources: Mapped[list["DataSource"]] = relationship("DataSource", back_populates="organization")
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="organization")
    alert_configs: Mapped[list["AlertConfig"]] = relationship("AlertConfig", back_populates="organization")
    invites: Mapped[list["Invite"]] = relationship("Invite", back_populates="organization")
    teams: Mapped[list["Team"]] = relationship("Team", back_populates="organization")
