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
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notify_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_team: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_status_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    daily_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    digest_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    mute_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates=None)
    organization: Mapped["Organization"] = relationship("Organization", back_populates=None)
