from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConversationStatus
from app.db.base import Base
from app.utils.uuid import generate_uuid4

if TYPE_CHECKING:
    from app.models.agent_message import AgentMessage
    from app.models.behavior_event import BehaviorEvent
    from app.models.driving_session import DrivingSession


class AgentConversation(Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('SAFETY', 'GENERAL_ASSISTANT')",
            name="ck_agent_conversations_mode",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'ABORTED')",
            name="ck_agent_conversations_status",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_agent_conversations_ended_at_after_started_at",
        ),
        CheckConstraint(
            "((status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status IN ('COMPLETED', 'ABORTED') AND ended_at IS NOT NULL))",
            name="ck_agent_conversations_status_end_state",
        ),
        Index("idx_agent_conversations_session_time", "session_id", "started_at"),
        Index("idx_agent_conversations_trigger_event", "trigger_behavior_event_id"),
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
    session_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey(
            "driving_sessions.id",
            name="fk_agent_conversations_session_id_driving_sessions",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    trigger_behavior_event_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey(
            "behavior_events.id",
            name="fk_agent_conversations_trigger_behavior_event_id_behavior_events",
            ondelete="SET NULL",
            onupdate="RESTRICT",
        ),
        nullable=True,
    )
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ConversationStatus.ACTIVE.value,
        server_default=text("'ACTIVE'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
    ended_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    session: Mapped[DrivingSession] = relationship(
        "DrivingSession",
        back_populates="agent_conversations",
    )
    trigger_behavior_event: Mapped[BehaviorEvent | None] = relationship(
        "BehaviorEvent",
        back_populates="agent_conversations",
    )
    messages: Mapped[list[AgentMessage]] = relationship(
        "AgentMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
