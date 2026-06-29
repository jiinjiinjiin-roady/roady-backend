from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.uuid import generate_uuid4

if TYPE_CHECKING:
    from app.models.agent_conversation import AgentConversation
    from app.models.tool_execution import ToolExecution


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        CheckConstraint(
            "sequence_no >= 1",
            name="ck_agent_messages_sequence_no",
        ),
        CheckConstraint(
            "role IN ('USER', 'AGENT', 'SYSTEM', 'TOOL')",
            name="ck_agent_messages_role",
        ),
        CheckConstraint(
            "input_type IS NULL OR input_type IN ('VOICE', 'TEXT', 'BUTTON', 'SYSTEM_EVENT')",
            name="ck_agent_messages_input_type",
        ),
        UniqueConstraint(
            "conversation_id",
            "sequence_no",
            name="uq_agent_messages_conversation_sequence",
        ),
        Index("idx_agent_messages_conversation_time", "conversation_id", "created_at"),
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
    conversation_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey(
            "agent_conversations.id",
            name="fk_agent_messages_conversation_id_agent_conversations",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        mysql.JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP(6)"),
    )

    conversation: Mapped[AgentConversation] = relationship(
        "AgentConversation",
        back_populates="messages",
    )
    tool_executions: Mapped[list[ToolExecution]] = relationship(
        "ToolExecution",
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
