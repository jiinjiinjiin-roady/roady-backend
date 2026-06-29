from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql

from app.core.enums import (
    AgentInputType,
    AgentMessageRole,
    ConversationMode,
    ConversationStatus,
    EmailStatus,
    FailureStage,
    ReportExportStatus,
    ReportPeriodType,
    ToolConfirmationStatus,
    ToolExecutionStatus,
)
from app.models import (
    AgentConversation,
    AgentMessage,
    BehaviorEvent,
    DriverProfile,
    DrivingSession,
    ReportExport,
    ToolExecution,
)


def constraint_names(model: type) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }


def unique_constraint_names(model: type) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def index_names(model: type) -> set[str]:
    return {index.name for index in model.__table__.indexes if isinstance(index, Index)}


def test_agent_conversation_schema_constraints_fks_and_relationships() -> None:
    table = AgentConversation.__table__

    assert table.name == "agent_conversations"
    assert set(table.columns.keys()) == {
        "id",
        "session_id",
        "trigger_behavior_event_id",
        "mode",
        "status",
        "started_at",
        "ended_at",
        "created_at",
    }
    assert isinstance(table.c.id.type, CHAR)
    assert table.c.id.type.length == 36
    assert table.c.id.default is not None
    assert isinstance(table.c.mode.type, String)
    assert table.c.mode.type.length == 30
    assert table.c.status.default.arg == ConversationStatus.ACTIVE.value
    assert isinstance(table.c.started_at.type, mysql.DATETIME)
    assert table.c.started_at.type.fsp == 6
    assert table.c.trigger_behavior_event_id.nullable
    assert constraint_names(AgentConversation) == {
        "ck_agent_conversations_mode",
        "ck_agent_conversations_status",
        "ck_agent_conversations_ended_at_after_started_at",
        "ck_agent_conversations_status_end_state",
    }
    assert {
        "idx_agent_conversations_session_time",
        "idx_agent_conversations_trigger_event",
    } <= index_names(AgentConversation)

    session_fk = next(iter(table.c.session_id.foreign_keys))
    assert isinstance(session_fk, ForeignKey)
    assert session_fk.target_fullname == "driving_sessions.id"
    assert session_fk.ondelete == "CASCADE"
    assert session_fk.onupdate == "RESTRICT"
    assert session_fk.constraint.name == "fk_agent_conversations_session_id_driving_sessions"

    event_fk = next(iter(table.c.trigger_behavior_event_id.foreign_keys))
    assert event_fk.target_fullname == "behavior_events.id"
    assert event_fk.ondelete == "SET NULL"
    assert event_fk.onupdate == "RESTRICT"
    assert (
        event_fk.constraint.name
        == "fk_agent_conversations_trigger_behavior_event_id_behavior_events"
    )

    assert DrivingSession.agent_conversations.property.back_populates == "session"
    assert DrivingSession.agent_conversations.property.cascade.delete_orphan
    assert BehaviorEvent.agent_conversations.property.back_populates == "trigger_behavior_event"
    assert not BehaviorEvent.agent_conversations.property.cascade.delete_orphan
    assert AgentConversation.messages.property.cascade.delete_orphan


def test_agent_message_schema_constraints_unique_json_and_relationships() -> None:
    table = AgentMessage.__table__

    assert table.name == "agent_messages"
    assert set(table.columns.keys()) == {
        "id",
        "conversation_id",
        "sequence_no",
        "role",
        "text",
        "intent",
        "input_type",
        "metadata_json",
        "created_at",
    }
    assert isinstance(table.c.id.type, CHAR)
    assert table.c.id.default is not None
    assert isinstance(table.c.sequence_no.type, mysql.INTEGER)
    assert table.c.sequence_no.type.unsigned
    assert isinstance(table.c.role.type, String)
    assert table.c.role.type.length == 20
    assert isinstance(table.c.text.type, Text)
    assert table.c.text.nullable
    assert isinstance(table.c.intent.type, String)
    assert table.c.intent.type.length == 100
    assert isinstance(table.c.input_type.type, String)
    assert table.c.input_type.type.length == 20
    assert isinstance(table.c.metadata_json.type, mysql.JSON)
    assert table.c.metadata_json.default is not None
    assert callable(table.c.metadata_json.default.arg)
    assert isinstance(table.c.created_at.type, mysql.DATETIME)
    assert table.c.created_at.type.fsp == 6
    assert constraint_names(AgentMessage) == {
        "ck_agent_messages_sequence_no",
        "ck_agent_messages_role",
        "ck_agent_messages_input_type",
    }
    assert unique_constraint_names(AgentMessage) == {
        "uq_agent_messages_conversation_sequence"
    }
    assert "idx_agent_messages_conversation_time" in index_names(AgentMessage)

    fk = next(iter(table.c.conversation_id.foreign_keys))
    assert fk.target_fullname == "agent_conversations.id"
    assert fk.ondelete == "CASCADE"
    assert fk.onupdate == "RESTRICT"
    assert fk.constraint.name == "fk_agent_messages_conversation_id_agent_conversations"
    assert AgentMessage.conversation.property.back_populates == "messages"
    assert AgentMessage.tool_executions.property.cascade.delete_orphan


def test_tool_execution_schema_constraints_json_defaults_and_relationships() -> None:
    table = ToolExecution.__table__

    assert table.name == "tool_executions"
    assert isinstance(table.c.id.type, CHAR)
    assert table.c.id.default is not None
    assert isinstance(table.c.tool_name.type, String)
    assert table.c.tool_name.type.length == 100
    assert isinstance(table.c.arguments_json.type, mysql.JSON)
    assert table.c.arguments_json.default is not None
    assert callable(table.c.arguments_json.default.arg)
    assert isinstance(table.c.result_json.type, mysql.JSON)
    assert table.c.result_json.nullable
    assert isinstance(table.c.confirmation_required.type, Boolean)
    assert table.c.confirmation_required.default.arg is False
    assert table.c.confirmation_status.default.arg == ToolConfirmationStatus.NOT_REQUIRED.value
    assert table.c.execution_status.default.arg == ToolExecutionStatus.PENDING.value
    assert isinstance(table.c.is_simulated.type, Boolean)
    assert table.c.is_simulated.default.arg is False
    assert isinstance(table.c.error_message.type, Text)
    assert table.c.error_message.nullable
    assert isinstance(table.c.created_at.type, mysql.DATETIME)
    assert isinstance(table.c.started_at.type, mysql.DATETIME)
    assert isinstance(table.c.completed_at.type, mysql.DATETIME)
    assert constraint_names(ToolExecution) == {
        "ck_tool_executions_confirmation_status",
        "ck_tool_executions_execution_status",
        "ck_tool_executions_completed_at_after_started_at",
        "ck_tool_executions_confirmation_required_status",
    }
    assert {
        "idx_tool_executions_message",
        "idx_tool_executions_execution_status",
    } <= index_names(ToolExecution)

    fk = next(iter(table.c.message_id.foreign_keys))
    assert fk.target_fullname == "agent_messages.id"
    assert fk.ondelete == "CASCADE"
    assert fk.onupdate == "RESTRICT"
    assert fk.constraint.name == "fk_tool_executions_message_id_agent_messages"
    assert ToolExecution.message.property.back_populates == "tool_executions"


def test_report_export_schema_constraints_json_defaults_and_relationships() -> None:
    table = ReportExport.__table__

    assert table.name == "report_exports"
    assert set(table.columns.keys()) == {
        "id",
        "profile_id",
        "period_type",
        "period_start",
        "period_end",
        "filter_options_json",
        "export_status",
        "file_name",
        "storage_key",
        "recipient_email",
        "email_status",
        "failure_stage",
        "failure_reason",
        "created_at",
        "completed_at",
        "emailed_at",
        "expires_at",
    }
    assert isinstance(table.c.id.type, CHAR)
    assert table.c.id.default is not None
    assert isinstance(table.c.period_type.type, String)
    assert table.c.period_type.type.length == 20
    assert isinstance(table.c.period_start.type, Date)
    assert isinstance(table.c.period_end.type, Date)
    assert isinstance(table.c.filter_options_json.type, mysql.JSON)
    assert table.c.filter_options_json.default is not None
    assert callable(table.c.filter_options_json.default.arg)
    assert table.c.export_status.default.arg == ReportExportStatus.PENDING.value
    assert isinstance(table.c.file_name.type, String)
    assert table.c.file_name.type.length == 255
    assert isinstance(table.c.storage_key.type, Text)
    assert isinstance(table.c.recipient_email.type, String)
    assert table.c.recipient_email.type.length == 320
    assert table.c.email_status.default.arg == EmailStatus.NOT_REQUESTED.value
    assert isinstance(table.c.failure_stage.type, String)
    assert isinstance(table.c.failure_reason.type, Text)
    assert constraint_names(ReportExport) == {
        "ck_report_exports_period_type",
        "ck_report_exports_export_status",
        "ck_report_exports_email_status",
        "ck_report_exports_failure_stage",
        "ck_report_exports_period_end_after_start",
        "ck_report_exports_completed_at_after_created_at",
        "ck_report_exports_emailed_at_after_created_at",
        "ck_report_exports_expires_at_after_created_at",
        "ck_report_exports_email_requires_recipient",
    }
    assert {
        "idx_report_exports_profile_created_at",
        "idx_report_exports_export_status",
        "idx_report_exports_email_status",
    } <= index_names(ReportExport)

    fk = next(iter(table.c.profile_id.foreign_keys))
    assert fk.target_fullname == "driver_profiles.id"
    assert fk.ondelete == "CASCADE"
    assert fk.onupdate == "RESTRICT"
    assert fk.constraint.name == "fk_report_exports_profile_id_driver_profiles"
    assert ReportExport.profile.property.back_populates == "report_exports"
    assert DriverProfile.report_exports.property.cascade.delete_orphan


def test_agent_report_enum_values() -> None:
    assert {item.value for item in ConversationMode} == {"SAFETY", "GENERAL_ASSISTANT"}
    assert {item.value for item in ConversationStatus} == {"ACTIVE", "COMPLETED", "ABORTED"}
    assert {item.value for item in AgentMessageRole} == {"USER", "AGENT", "SYSTEM", "TOOL"}
    assert {item.value for item in AgentInputType} == {
        "VOICE",
        "TEXT",
        "BUTTON",
        "SYSTEM_EVENT",
    }
    assert {item.value for item in ToolConfirmationStatus} == {
        "NOT_REQUIRED",
        "PENDING",
        "ACCEPTED",
        "REJECTED",
    }
    assert {item.value for item in ToolExecutionStatus} == {
        "PENDING",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    }
    assert {item.value for item in ReportPeriodType} == {"WEEKLY", "MONTHLY", "CUSTOM"}
    assert {item.value for item in ReportExportStatus} == {
        "PENDING",
        "GENERATING",
        "COMPLETED",
        "FAILED",
    }
    assert {item.value for item in EmailStatus} == {
        "NOT_REQUESTED",
        "PENDING",
        "SENT",
        "FAILED",
    }
    assert {item.value for item in FailureStage} == {"EXPORT", "EMAIL"}
