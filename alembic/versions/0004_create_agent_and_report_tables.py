"""create agent conversation and report export tables

Revision ID: 0004_agent_report_tables
Revises: 0003_driving_safety_tables
Create Date: 2026-06-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0004_agent_report_tables"
down_revision: str | None = "0003_driving_safety_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("session_id", sa.CHAR(length=36), nullable=False),
        sa.Column("trigger_behavior_event_id", sa.CHAR(length=36), nullable=True),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("ended_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('SAFETY', 'GENERAL_ASSISTANT')",
            name="ck_agent_conversations_mode",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'ABORTED')",
            name="ck_agent_conversations_status",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_agent_conversations_ended_at_after_started_at",
        ),
        sa.CheckConstraint(
            "((status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status IN ('COMPLETED', 'ABORTED') AND ended_at IS NOT NULL))",
            name="ck_agent_conversations_status_end_state",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["driving_sessions.id"],
            name="fk_agent_conversations_session_id_driving_sessions",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_behavior_event_id"],
            ["behavior_events.id"],
            name="fk_agent_conversations_trigger_behavior_event_id_behavior_events",
            ondelete="SET NULL",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_agent_conversations_session_time",
        "agent_conversations",
        ["session_id", "started_at"],
    )
    op.create_index(
        "idx_agent_conversations_trigger_event",
        "agent_conversations",
        ["trigger_behavior_event_id"],
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("conversation_id", sa.CHAR(length=36), nullable=False),
        sa.Column("sequence_no", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("intent", sa.String(length=100), nullable=True),
        sa.Column("input_type", sa.String(length=20), nullable=True),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_no >= 1",
            name="ck_agent_messages_sequence_no",
        ),
        sa.CheckConstraint(
            "role IN ('USER', 'AGENT', 'SYSTEM', 'TOOL')",
            name="ck_agent_messages_role",
        ),
        sa.CheckConstraint(
            "input_type IS NULL OR input_type IN ('VOICE', 'TEXT', 'BUTTON', 'SYSTEM_EVENT')",
            name="ck_agent_messages_input_type",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.id"],
            name="fk_agent_messages_conversation_id_agent_conversations",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence_no",
            name="uq_agent_messages_conversation_sequence",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_agent_messages_conversation_time",
        "agent_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("message_id", sa.CHAR(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("arguments_json", mysql.JSON(), nullable=False),
        sa.Column("result_json", mysql.JSON(), nullable=True),
        sa.Column(
            "confirmation_required",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "confirmation_status",
            sa.String(length=20),
            server_default=sa.text("'NOT_REQUIRED'"),
            nullable=False,
        ),
        sa.Column(
            "execution_status",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "confirmation_status IN ('NOT_REQUIRED', 'PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_tool_executions_confirmation_status",
        ),
        sa.CheckConstraint(
            "execution_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_tool_executions_execution_status",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_tool_executions_completed_at_after_started_at",
        ),
        sa.CheckConstraint(
            "((confirmation_required = 0 AND confirmation_status = 'NOT_REQUIRED') OR "
            "(confirmation_required = 1 AND confirmation_status IN "
            "('PENDING', 'ACCEPTED', 'REJECTED')))",
            name="ck_tool_executions_confirmation_required_status",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["agent_messages.id"],
            name="fk_tool_executions_message_id_agent_messages",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_tool_executions_message", "tool_executions", ["message_id"])
    op.create_index(
        "idx_tool_executions_execution_status",
        "tool_executions",
        ["execution_status"],
    )

    op.create_table(
        "report_exports",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("profile_id", sa.CHAR(length=36), nullable=False),
        sa.Column("period_type", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filter_options_json", mysql.JSON(), nullable=False),
        sa.Column(
            "export_status",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column(
            "email_status",
            sa.String(length=20),
            server_default=sa.text("'NOT_REQUESTED'"),
            nullable=False,
        ),
        sa.Column("failure_stage", sa.String(length=20), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("emailed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "period_type IN ('WEEKLY', 'MONTHLY', 'CUSTOM')",
            name="ck_report_exports_period_type",
        ),
        sa.CheckConstraint(
            "export_status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')",
            name="ck_report_exports_export_status",
        ),
        sa.CheckConstraint(
            "email_status IN ('NOT_REQUESTED', 'PENDING', 'SENT', 'FAILED')",
            name="ck_report_exports_email_status",
        ),
        sa.CheckConstraint(
            "failure_stage IS NULL OR failure_stage IN ('EXPORT', 'EMAIL')",
            name="ck_report_exports_failure_stage",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_report_exports_period_end_after_start",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_report_exports_completed_at_after_created_at",
        ),
        sa.CheckConstraint(
            "emailed_at IS NULL OR emailed_at >= created_at",
            name="ck_report_exports_emailed_at_after_created_at",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at >= created_at",
            name="ck_report_exports_expires_at_after_created_at",
        ),
        sa.CheckConstraint(
            "email_status = 'NOT_REQUESTED' OR recipient_email IS NOT NULL",
            name="ck_report_exports_email_requires_recipient",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["driver_profiles.id"],
            name="fk_report_exports_profile_id_driver_profiles",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_report_exports_profile_created_at",
        "report_exports",
        ["profile_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_report_exports_export_status", "report_exports", ["export_status"])
    op.create_index("idx_report_exports_email_status", "report_exports", ["email_status"])


def downgrade() -> None:
    op.drop_table("report_exports")

    op.drop_table("tool_executions")

    op.drop_table("agent_messages")

    op.drop_table("agent_conversations")
