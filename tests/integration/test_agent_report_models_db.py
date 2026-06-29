import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db.session import AsyncSessionLocal, dispose_engine
from app.models import (
    Account,
    AgentConversation,
    AgentMessage,
    BehaviorEvent,
    DriverProfile,
    DrivingSession,
    ReportExport,
    ToolExecution,
)

pytestmark = pytest.mark.skipif(
    not (os.getenv("MYSQL_HOST") and os.getenv("MYSQL_PASSWORD")),
    reason="MySQL integration tests require Docker Compose database environment.",
)


def now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def make_account() -> Account:
    return Account(id=str(uuid4()), email=f"agent-report-{uuid4().hex}@example.com")


def make_profile(account_id: str, display_name: str = "Agent Driver") -> DriverProfile:
    return DriverProfile(
        account_id=account_id,
        display_name=display_name,
        agent_call_name=display_name,
    )


def make_session(profile_id: str) -> DrivingSession:
    return DrivingSession(
        profile_id=profile_id,
        started_at=now_utc_naive(),
        model_version="vit-test",
        policy_version="policy-test",
    )


def make_behavior_event(session_id: str) -> BehaviorEvent:
    return BehaviorEvent(
        session_id=session_id,
        behavior_type="PHONE_USE",
        started_at=now_utc_naive(),
        average_confidence=Decimal("0.8000"),
        maximum_confidence=Decimal("0.9000"),
        driving_state="MOVING",
        speed_kph=Decimal("35.50"),
        risk_level=2,
    )


def make_conversation(
    session_id: str,
    trigger_behavior_event_id: str | None = None,
    mode: str = "SAFETY",
) -> AgentConversation:
    return AgentConversation(
        session_id=session_id,
        trigger_behavior_event_id=trigger_behavior_event_id,
        mode=mode,
    )


def make_message(
    conversation_id: str,
    sequence_no: int = 1,
    role: str = "USER",
    input_type: str | None = "VOICE",
) -> AgentMessage:
    return AgentMessage(
        conversation_id=conversation_id,
        sequence_no=sequence_no,
        role=role,
        text="Navigate home.",
        intent="NAVIGATE",
        input_type=input_type,
        metadata_json={},
    )


def make_tool_execution(
    message_id: str,
    confirmation_required: bool = False,
    confirmation_status: str = "NOT_REQUIRED",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ToolExecution:
    return ToolExecution(
        message_id=message_id,
        tool_name="navigation.start",
        arguments_json={"destination": "home"},
        result_json={"ok": True},
        confirmation_required=confirmation_required,
        confirmation_status=confirmation_status,
        started_at=started_at,
        completed_at=completed_at,
    )


def make_report_export(
    profile_id: str,
    period_start: date = date(2026, 6, 1),
    period_end: date = date(2026, 6, 7),
    email_status: str = "NOT_REQUESTED",
    recipient_email: str | None = None,
) -> ReportExport:
    return ReportExport(
        profile_id=profile_id,
        period_type="WEEKLY",
        period_start=period_start,
        period_end=period_end,
        filter_options_json={},
        email_status=email_status,
        recipient_email=recipient_email,
    )


async def assert_integrity_error(instance: object) -> None:
    async with AsyncSessionLocal() as session:
        session.add(instance)
        with pytest.raises((IntegrityError, OperationalError)):
            await session.commit()
        await session.rollback()


async def delete_test_accounts(*account_ids: str) -> None:
    async with AsyncSessionLocal() as session:
        if account_ids:
            await session.execute(delete(Account).where(Account.id.in_(account_ids)))
        await session.commit()


async def create_account_profile_session(
    include_event: bool = False,
) -> tuple[str, str, str, str | None]:
    account = make_account()
    profile = make_profile(account.id)

    async with AsyncSessionLocal() as session:
        session.add(account)
        await session.flush()
        session.add(profile)
        await session.flush()
        driving_session = make_session(profile.id)
        session.add(driving_session)
        await session.flush()
        event_id: str | None = None
        if include_event:
            event = make_behavior_event(driving_session.id)
            session.add(event)
            await session.flush()
            event_id = event.id
        await session.commit()

    return account.id, profile.id, driving_session.id, event_id


async def create_conversation_message_tool(
    session_id: str,
    trigger_behavior_event_id: str | None = None,
) -> tuple[str, str, str]:
    async with AsyncSessionLocal() as session:
        conversation = make_conversation(session_id, trigger_behavior_event_id)
        session.add(conversation)
        await session.flush()
        message = make_message(conversation.id)
        session.add(message)
        await session.flush()
        tool_execution = make_tool_execution(message.id)
        session.add(tool_execution)
        await session.commit()

    return conversation.id, message.id, tool_execution.id


async def test_session_conversation_and_messages_can_be_created_with_sequence() -> None:
    account_id, _, session_id, event_id = await create_account_profile_session(include_event=True)

    try:
        async with AsyncSessionLocal() as session:
            conversation = make_conversation(session_id, event_id)
            session.add(conversation)
            await session.flush()
            session.add_all(
                [
                    make_message(conversation.id, sequence_no=1, role="USER"),
                    make_message(conversation.id, sequence_no=2, role="AGENT", input_type=None),
                ]
            )
            await session.commit()
            conversation_id = conversation.id

        async with AsyncSessionLocal() as session:
            message_count = await session.scalar(
                select(func.count())
                .select_from(AgentMessage)
                .where(AgentMessage.conversation_id == conversation_id)
            )

        assert message_count == 2
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_agent_message_duplicate_sequence_fails_per_conversation() -> None:
    account_id, _, session_id, _ = await create_account_profile_session()

    try:
        async with AsyncSessionLocal() as session:
            conversation = make_conversation(session_id)
            session.add(conversation)
            await session.flush()
            session.add(make_message(conversation.id, sequence_no=1))
            await session.commit()
            conversation_id = conversation.id

        await assert_integrity_error(make_message(conversation_id, sequence_no=1))
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_tool_execution_create_and_checks_are_enforced() -> None:
    account_id, _, session_id, _ = await create_account_profile_session()
    _, message_id, tool_execution_id = await create_conversation_message_tool(session_id)
    started_at = now_utc_naive()

    try:
        async with AsyncSessionLocal() as session:
            tool_execution_count = await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(ToolExecution.id == tool_execution_id)
            )

        assert tool_execution_count == 1

        await assert_integrity_error(
            make_tool_execution(
                message_id,
                confirmation_required=False,
                confirmation_status="PENDING",
            )
        )
        await assert_integrity_error(
            make_tool_execution(
                message_id,
                started_at=started_at,
                completed_at=started_at - timedelta(seconds=1),
            )
        )
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_report_export_create_and_checks_are_enforced() -> None:
    account_id, profile_id, _, _ = await create_account_profile_session()

    try:
        async with AsyncSessionLocal() as session:
            report_export = make_report_export(profile_id)
            session.add(report_export)
            await session.commit()
            report_export_id = report_export.id

        async with AsyncSessionLocal() as session:
            report_export_count = await session.scalar(
                select(func.count())
                .select_from(ReportExport)
                .where(ReportExport.id == report_export_id)
            )

        assert report_export_count == 1

        await assert_integrity_error(
            make_report_export(
                profile_id,
                period_start=date(2026, 6, 7),
                period_end=date(2026, 6, 1),
            )
        )
        await assert_integrity_error(
            make_report_export(
                profile_id,
                email_status="PENDING",
                recipient_email=None,
            )
        )
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_session_delete_cascades_conversation_message_and_tool_execution() -> None:
    account_id, _, session_id, _ = await create_account_profile_session()
    conversation_id, message_id, tool_execution_id = await create_conversation_message_tool(
        session_id
    )

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DrivingSession).where(DrivingSession.id == session_id))
            await session.commit()

        async with AsyncSessionLocal() as session:
            conversation_count = await session.scalar(
                select(func.count())
                .select_from(AgentConversation)
                .where(AgentConversation.id == conversation_id)
            )
            message_count = await session.scalar(
                select(func.count()).select_from(AgentMessage).where(AgentMessage.id == message_id)
            )
            tool_execution_count = await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(ToolExecution.id == tool_execution_id)
            )

        assert conversation_count == 0
        assert message_count == 0
        assert tool_execution_count == 0
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_behavior_event_delete_sets_conversation_trigger_to_null() -> None:
    account_id, _, session_id, event_id = await create_account_profile_session(include_event=True)
    assert event_id is not None

    try:
        conversation_id, _, _ = await create_conversation_message_tool(session_id, event_id)

        async with AsyncSessionLocal() as session:
            await session.execute(delete(BehaviorEvent).where(BehaviorEvent.id == event_id))
            await session.commit()

        async with AsyncSessionLocal() as session:
            conversation = await session.get(AgentConversation, conversation_id)
            event_count = await session.scalar(
                select(func.count()).select_from(BehaviorEvent).where(BehaviorEvent.id == event_id)
            )

        assert event_count == 0
        assert conversation is not None
        assert conversation.trigger_behavior_event_id is None
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_profile_delete_cascades_report_exports() -> None:
    account_id, profile_id, _, _ = await create_account_profile_session()

    try:
        async with AsyncSessionLocal() as session:
            report_export = make_report_export(profile_id)
            session.add(report_export)
            await session.commit()
            report_export_id = report_export.id

        async with AsyncSessionLocal() as session:
            await session.execute(delete(DriverProfile).where(DriverProfile.id == profile_id))
            await session.commit()

        async with AsyncSessionLocal() as session:
            report_count = await session.scalar(
                select(func.count())
                .select_from(ReportExport)
                .where(ReportExport.id == report_export_id)
            )

        assert report_count == 0
    finally:
        await delete_test_accounts(account_id)
        await dispose_engine()


async def test_no_direct_report_to_session_link_tables_exist() -> None:
    async with AsyncSessionLocal() as session:
        tables_result = await session.execute(text("SHOW TABLES"))
        tables = set(tables_result.scalars().all())

    assert "report_session_links" not in tables
    assert "report_export_sessions" not in tables
    assert "driving_session_report_exports" not in tables
    await dispose_engine()
