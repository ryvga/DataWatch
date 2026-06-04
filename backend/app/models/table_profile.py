import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TableProfile(Base):
    __tablename__ = "table_profiles"
    __table_args__ = (
        Index("ix_table_profiles_table_collected", "table_id", "collected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    freshness_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    column_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    profiling_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    table: Mapped["MonitoredTable"] = relationship("MonitoredTable", back_populates="profiles")
    check_results: Mapped[list["CheckResult"]] = relationship("CheckResult", back_populates="profile")
