import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (
        Index("ix_check_results_table_checked", "table_id", "checked_at"),
        Index("ix_check_results_status_checked", "status", "checked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("table_profiles.id", ondelete="SET NULL"), nullable=True
    )
    check_type: Mapped[str] = mapped_column(String(100), nullable=False)   # z_score | isoforest | schema | freshness
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)        # passed | failed | error
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_range: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deviation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    table: Mapped["MonitoredTable"] = relationship("MonitoredTable", back_populates="check_results")
    profile: Mapped["TableProfile | None"] = relationship("TableProfile", back_populates="check_results")
