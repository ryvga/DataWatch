import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.database import Base


class Monitor(Base):
    """Stable monitor identity; mutable state points at immutable revisions."""

    __tablename__ = "monitors"
    __table_args__ = (
        UniqueConstraint("org_id", "table_id", "name", name="uq_monitors_org_table_name"),
        UniqueConstraint("org_id", "id", name="uq_monitors_org_id"),
        UniqueConstraint("id", "table_id", name="uq_monitors_id_table"),
        ForeignKeyConstraint(
            ["id", "active_revision_id"],
            ["monitor_revisions.monitor_id", "monitor_revisions.id"],
            name="fk_monitors_active_revision_owner",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_monitors_org_status", "org_id", "status"),
        Index("ix_monitors_table_id", "table_id"),
        CheckConstraint("mode IN ('dsl', 'legacy_sql')", name="ck_monitors_mode"),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')",
            name="ck_monitors_status",
        ),
        CheckConstraint(
            "status != 'active' OR active_revision_id IS NOT NULL",
            name="ck_monitors_active_revision",
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
    active_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
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
        "MonitorRevision",
        back_populates="monitor",
        cascade="all, delete-orphan",
        foreign_keys="MonitorRevision.monitor_id",
    )
    active_revision: Mapped["MonitorRevision | None"] = relationship(
        "MonitorRevision",
        foreign_keys=[active_revision_id],
        post_update=True,
    )
    runs: Mapped[list["MonitorRun"]] = relationship(
        "MonitorRun",
        back_populates="monitor",
        cascade="all, delete-orphan",
        primaryjoin=lambda: Monitor.id == foreign(MonitorRun.monitor_id),
    )


class MonitorRevision(Base):
    """Append-only canonical definition snapshot."""

    __tablename__ = "monitor_revisions"
    __table_args__ = (
        UniqueConstraint("monitor_id", "revision", name="uq_monitor_revisions_number"),
        UniqueConstraint("monitor_id", "id", name="uq_monitor_revisions_monitor_id"),
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

    monitor: Mapped[Monitor] = relationship(
        "Monitor",
        back_populates="revisions",
        foreign_keys=[monitor_id],
    )
    runs: Mapped[list["MonitorRun"]] = relationship(
        "MonitorRun",
        back_populates="revision",
        primaryjoin=lambda: MonitorRevision.id == foreign(MonitorRun.revision_id),
    )


class MonitorRun(Base):
    """Execution audit record; terminal rows are immutable application state."""

    __tablename__ = "monitor_runs"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_monitor_runs_idempotency"),
        UniqueConstraint("monitor_id", "id", name="uq_monitor_runs_monitor_id"),
        ForeignKeyConstraint(
            ["org_id", "monitor_id"],
            ["monitors.org_id", "monitors.id"],
            name="fk_monitor_runs_monitor_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["monitor_id", "revision_id"],
            ["monitor_revisions.monitor_id", "monitor_revisions.id"],
            name="fk_monitor_runs_revision_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["monitor_id", "table_id"],
            ["monitors.id", "monitors.table_id"],
            name="fk_monitor_runs_table_owner",
            ondelete="CASCADE",
        ),
        Index("ix_monitor_runs_monitor_started", "monitor_id", "started_at"),
        Index("ix_monitor_runs_revision_id", "revision_id"),
        Index("ix_monitor_runs_table_id", "table_id"),
        Index(
            "uq_monitor_runs_profile_trigger",
            "monitor_id",
            "revision_id",
            "profile_id",
            unique=True,
            postgresql_where=text("profile_id IS NOT NULL"),
        ),
        Index(
            "uq_monitor_runs_one_running",
            "monitor_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'error', 'cancelled')",
            name="ck_monitor_runs_status",
        ),
        CheckConstraint(
            "(trigger_type = 'on_profile' AND profile_id IS NOT NULL) OR "
            "(trigger_type = 'manual' AND profile_id IS NULL)",
            name="ck_monitor_runs_trigger_profile",
        ),
        CheckConstraint("attempt > 0", name="ck_monitor_runs_attempt_positive"),
        CheckConstraint(
            "(status = 'queued' AND claim_token IS NULL AND started_at IS NULL "
            "AND lease_expires_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'running' AND claim_token IS NOT NULL AND started_at IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('passed', 'failed', 'error', 'cancelled') "
            "AND completed_at IS NOT NULL AND claim_token IS NULL "
            "AND lease_expires_at IS NULL)",
            name="ck_monitor_runs_lifecycle",
        ),
        CheckConstraint(
            "status NOT IN ('passed', 'failed') OR (measurements IS NOT NULL AND result IS NOT NULL)",
            name="ck_monitor_runs_terminal_result",
        ),
        CheckConstraint(
            "status != 'error' OR (error_code IS NOT NULL AND error IS NOT NULL)",
            name="ck_monitor_runs_error_payload",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    sequence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    planner_version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    measurements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    monitor: Mapped[Monitor] = relationship(
        "Monitor",
        back_populates="runs",
        primaryjoin=lambda: Monitor.id == foreign(MonitorRun.monitor_id),
    )
    revision: Mapped[MonitorRevision] = relationship(
        "MonitorRevision",
        back_populates="runs",
        primaryjoin=lambda: MonitorRevision.id == foreign(MonitorRun.revision_id),
    )


class MonitorEvaluationState(Base):
    """Mutable per-monitor policy state, separate from immutable terminal run audits."""

    __tablename__ = "monitor_evaluation_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "monitor_id"],
            ["monitors.org_id", "monitors.id"],
            name="fk_monitor_eval_monitor_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["monitor_id", "revision_id"],
            ["monitor_revisions.monitor_id", "monitor_revisions.id"],
            name="fk_monitor_eval_revision_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["monitor_id", "last_run_id"],
            ["monitor_runs.monitor_id", "monitor_runs.id"],
            name="fk_monitor_eval_last_run_owner",
        ),
        Index("ix_monitor_evaluation_states_org_id", "org_id"),
        CheckConstraint("phase IN ('healthy', 'breached')", name="ck_monitor_eval_phase"),
        CheckConstraint(
            "breach_streak >= 0 AND recovery_streak >= 0",
            name="ck_monitor_eval_streaks_nonnegative",
        ),
        CheckConstraint("version > 0", name="ck_monitor_eval_version_positive"),
    )

    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="healthy")
    breach_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovery_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_sequence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
