from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, Boolean, CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ToolConfirmationStatus, ToolExecutionStatus
from app.db.base import Base
from app.utils.uuid import generate_uuid4

if TYPE_CHECKING:
    from app.models.agent_message import AgentMessage


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(
            "confirmation_status IN ('NOT_REQUIRED', 'PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_tool_executions_confirmation_status",
        ),
        CheckConstraint(
            "execution_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_tool_executions_execution_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_tool_executions_completed_at_after_started_at",
        ),
        CheckConstraint(
            "((confirmation_required = 0 AND confirmation_status = 'NOT_REQUIRED') OR "
            "(confirmation_required = 1 AND confirmation_status IN "
            "('PENDING', 'ACCEPTED', 'REJECTED')))",
            name="ck_tool_executions_confirmation_required_status",
        ),
        Index("idx_tool_executions_message", "message_id"),
        Index("idx_tool_executions_execution_status", "execution_status"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        nullable=False,
        default=generate_uuid4,
    )
    message_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey(
            "agent_messages.id",
            name="fk_tool_executions_message_id_agent_messages",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(
        mysql.JSON,
        nullable=False,
        default=dict,
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(mysql.JSON, nullable=True)
    confirmation_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    confirmation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ToolConfirmationStatus.NOT_REQUIRED.value,
        server_default=text("'NOT_REQUIRED'"),
    )
    execution_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ToolExecutionStatus.PENDING.value,
        server_default=text("'PENDING'"),
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
    started_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)

    message: Mapped[AgentMessage] = relationship(
        "AgentMessage",
        back_populates="tool_executions",
    )
