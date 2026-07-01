import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import DrivingState
from app.realtime.session_runtime import SessionRuntimeRegistry


@pytest.mark.asyncio
async def test_runtime_initial_fields_and_touch_methods() -> None:
    registry = SessionRuntimeRegistry()
    connected_at = datetime(2026, 6, 28, 3, 10, tzinfo=UTC)

    runtime = await registry.get_or_create("session-1", connected_at=connected_at)

    assert runtime.session_id == "session-1"
    assert runtime.connected_at == connected_at
    assert runtime.last_message_at == connected_at
    assert runtime.last_heartbeat_at == connected_at
    assert runtime.current_latitude is None
    assert runtime.current_longitude is None
    assert runtime.current_speed_kph is None
    assert runtime.driving_state == DrivingState.UNKNOWN
    assert runtime.last_location_persisted_at is None
    assert runtime.active_behavior_event_id is None
    assert runtime.current_intervention_id is None
    assert runtime.active_conversation_id is None
    assert registry.count == 1

    message_at = connected_at + timedelta(seconds=3)
    heartbeat_at = connected_at + timedelta(seconds=5)

    await registry.touch_message("session-1", message_at)
    assert runtime.last_message_at == message_at
    assert runtime.last_heartbeat_at == connected_at

    await registry.touch_heartbeat("session-1", heartbeat_at)
    assert runtime.last_message_at == heartbeat_at
    assert runtime.last_heartbeat_at == heartbeat_at


@pytest.mark.asyncio
async def test_registry_reuses_removes_and_clears_runtime() -> None:
    registry = SessionRuntimeRegistry()

    first = await registry.get_or_create("session-1")
    second = await registry.get_or_create("session-1")

    assert first is second
    assert registry.count == 1
    assert await registry.get("session-1") is first

    assert await registry.remove("missing") is False
    assert await registry.remove("session-1") is True
    assert registry.count == 0

    await registry.get_or_create("session-1")
    await registry.get_or_create("session-2")
    assert registry.count == 2
    await registry.clear()
    assert registry.count == 0


@pytest.mark.asyncio
async def test_concurrent_get_or_create_creates_one_runtime() -> None:
    registry = SessionRuntimeRegistry()

    runtimes = await asyncio.gather(
        *(registry.get_or_create("session-1") for _ in range(20)),
    )

    assert len({id(runtime) for runtime in runtimes}) == 1
    assert registry.count == 1
