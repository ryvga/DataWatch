import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MonitoredTable(Base):
    __tablename__ = "monitored_tables"
    __table_args__ = (
        UniqueConstraint("source_id", "schema_name", "table_name", name="uq_monitored_table_source_schema_table"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    freshness_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    sensitivity: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)  # z-score threshold
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dbt_model_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    autopilot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    check_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_profiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    data_source: Mapped["DataSource"] = relationship("DataSource", back_populates="monitored_tables")
    profiles: Mapped[list["TableProfile"]] = relationship("TableProfile", back_populates="table")
    check_results: Mapped[list["CheckResult"]] = relationship("CheckResult", back_populates="table")
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="table")
    alert_configs: Mapped[list["AlertConfig"]] = relationship("AlertConfig", back_populates="table")
    custom_monitors: Mapped[list["CustomMonitor"]] = relationship("CustomMonitor", back_populates="table")
    owner_team: Mapped["Team | None"] = relationship("Team", foreign_keys=[owner_team_id], lazy="select")
    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_user_id], lazy="select")
