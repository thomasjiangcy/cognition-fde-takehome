"""Create generic trigger events and workflow runs.

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trigger_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=True),
        sa.Column("subject_type", sa.String(length=64), nullable=True),
        sa.Column("subject_id", sa.String(length=255), nullable=True),
        sa.Column("subject_title", sa.Text(), nullable=True),
        sa.Column("subject_url", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trigger_events"),
        sa.UniqueConstraint(
            "source",
            "external_id",
            name="uq_trigger_events_source_external_id",
        ),
    )
    op.create_index(
        "ix_trigger_events_received_at",
        "trigger_events",
        ["received_at"],
        unique=False,
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trigger_event_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_name", sa.String(length=128), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "queued",
                "in_progress",
                "completed",
                "failed",
                name="workflow_run_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("devin_session_id", sa.String(length=255), nullable=True),
        sa.Column("devin_status", sa.String(length=64), nullable=True),
        sa.Column("devin_status_detail", sa.String(length=128), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_status_sync_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["trigger_event_id"],
            ["trigger_events.id"],
            name="fk_workflow_runs_trigger_event_id_trigger_events",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.UniqueConstraint(
            "devin_session_id",
            name="uq_workflow_runs_devin_session_id",
        ),
        sa.UniqueConstraint(
            "trigger_event_id",
            "workflow_name",
            name="uq_workflow_runs_trigger_event_id_workflow_name",
        ),
    )
    op.create_index(
        "ix_workflow_runs_created_at",
        "workflow_runs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_runs_state",
        "workflow_runs",
        ["state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_state", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_created_at", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_trigger_events_received_at", table_name="trigger_events")
    op.drop_table("trigger_events")
