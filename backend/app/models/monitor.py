import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Monitor(Base):
    """Stable monitor identity; mutable state points at immutable revisions."""

    __tablename__ = "monitors"
    __table_args__ = (
        UniqueConstraint("org_id", "table_id", "name", name="uq_monitors_org_table_name"),
        Index("ix_monitors_org_status", "org_id", "status"),
        Index("ix_monitors_table_id", "table_id"),
        CheckConstraint("mode IN ('dsl', 'legacy_sql')", name="ck_monitors_mode"),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')",
            name="ck_monitors_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="dsl")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revisions: Mapped[list["MonitorRevision"]] = relationship(
        "MonitorRevision", back_populates="monitor", cascade="all, delete-orphan"
    )
    runs: Mapped[list["MonitorRun"]] = relationship(
        "MonitorRun", back_populates="monitor", cascade="all, delete-orphan"
    )


class MonitorRevision(Base):
    """Append-only canonical definition snapshot."""

    __tablename__ = "monitor_revisions"
    __table_args__ = (
        UniqueConstraint("monitor_id", "revision", name="uq_monitor_revisions_number"),
        Index("ix_monitor_revisions_hash", "definition_hash"),
        Index("ix_monitor_revisions_monitor_id", "monitor_id"),
        CheckConstraint("revision > 0", name="ck_monitor_revisions_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="valid")
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    monitor: Mapped[Monitor] = relationship("Monitor", back_populates="revisions")
    runs: Mapped[list["MonitorRun"]] = relationship("MonitorRun", back_populates="revision")


class MonitorRun(Base):
    """Immutable execution audit record; execution will be added by typed compilers."""

    __tablename__ = "monitor_runs"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_monitor_runs_idempotency"),
        Index("ix_monitor_runs_monitor_started", "monitor_id", "started_at"),
        Index("ix_monitor_runs_revision_id", "revision_id"),
        Index("ix_monitor_runs_table_id", "table_id"),
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'error', 'cancelled')",
            name="ck_monitor_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitor_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    measurements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    monitor: Mapped[Monitor] = relationship("Monitor", back_populates="runs")
    revision: Mapped[MonitorRevision] = relationship("MonitorRevision", back_populates="runs")
