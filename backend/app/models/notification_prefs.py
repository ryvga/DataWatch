"""User notification preference model.

This table is added by the notifications migration (assumed to exist at runtime).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserNotificationPrefs(Base):
    __tablename__ = "user_notification_prefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Per-event toggles (all default True — opt-out model)
    notify_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    notify_team: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    notify_status_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Daily digest
    daily_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    digest_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)  # UTC hour 0-23

    # Snooze / DND
    mute_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="notification_prefs")
    organization: Mapped["Organization"] = relationship("Organization")
