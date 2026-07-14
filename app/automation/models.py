from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WorkflowRunState(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


def _workflow_run_state_values(
    enum_class: type[WorkflowRunState],
) -> list[str]:
    return [member.value for member in enum_class]


class TriggerEvent(Base):
    __tablename__ = "trigger_events"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_trigger_events_source_external_id",
        ),
        Index("ix_trigger_events_received_at", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(128))
    action: Mapped[str | None] = mapped_column(String(128))
    subject_type: Mapped[str | None] = mapped_column(String(64))
    subject_id: Mapped[str | None] = mapped_column(String(255))
    subject_title: Mapped[str | None] = mapped_column(Text)
    subject_url: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="trigger_event",
        cascade="all, delete-orphan",
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint(
            "trigger_event_id",
            "workflow_name",
            name="uq_workflow_runs_trigger_event_id_workflow_name",
        ),
        Index("ix_workflow_runs_state", "state"),
        Index("ix_workflow_runs_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trigger_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("trigger_events.id", ondelete="CASCADE")
    )
    workflow_name: Mapped[str] = mapped_column(String(128))
    state: Mapped[WorkflowRunState] = mapped_column(
        Enum(
            WorkflowRunState,
            name="workflow_run_state",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=_workflow_run_state_values,
        ),
        default=WorkflowRunState.QUEUED,
    )
    devin_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    devin_status: Mapped[str | None] = mapped_column(String(64))
    devin_status_detail: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_status_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    trigger_event: Mapped[TriggerEvent] = relationship(back_populates="workflow_runs")
