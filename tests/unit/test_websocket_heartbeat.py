import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from starlette.websockets import WebSocketState

from app.realtime.connection_manager import ConnectionManager
from app.realtime.heartbeat import HeartbeatController
from app.realtime.session_runtime import SessionRuntimeRegistry


class FakeWebSocket:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.sent: list[dict[str, Any]] = []
        self.close_calls: list[tuple[int, str]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    async def close(self, *, code: int, reason: str) -> None:
        self.application_state = WebSocketState.DISCONNECTED
        self.close_calls.append((code, reason))


@pytest.mark.asyncio
async def test_heartbeat_sends_periodic_ping_without_long_wait() -> None:
    manager = ConnectionManager()
    registry = SessionRuntimeRegistry()
    websocket = FakeWebSocket()
    now = datetime(2026, 6, 28, 3, 10, tzinfo=UTC)
    await manager.register("session-1", websocket)
    await registry.get_or_create("session-1", connected_at=now)
    sleep_calls = 0
    blocker = asyncio.Event()

    async def fake_sleep(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            return
        await blocker.wait()

    controller = HeartbeatController(
        session_id="session-1",
        websocket=websocket,
        connection_manager=manager,
        runtime_registry=registry,
        interval_seconds=10,
        timeout_seconds=30,
        clock=lambda: now + timedelta(seconds=10),
        sleep=fake_sleep,
    )
    task = asyncio.create_task(controller.run())

    while not websocket.sent:
        await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert websocket.sent[0]["type"] == "PING"
    assert websocket.sent[0]["occurredAt"] == "2026-06-28T03:10:10.000000Z"
    assert websocket.close_calls == []


@pytest.mark.asyncio
async def test_pong_extends_heartbeat_timeout() -> None:
    manager = ConnectionManager()
    registry = SessionRuntimeRegistry()
    websocket = FakeWebSocket()
    now = datetime(2026, 6, 28, 3, 10, tzinfo=UTC)
    await manager.register("session-1", websocket)
    await registry.get_or_create("session-1", connected_at=now - timedelta(seconds=60))
    await registry.touch_heartbeat("session-1", now)
    sleep_calls = 0
    blocker = asyncio.Event()

    async def fake_sleep(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            return
        await blocker.wait()

    controller = HeartbeatController(
        session_id="session-1",
        websocket=websocket,
        connection_manager=manager,
        runtime_registry=registry,
        interval_seconds=10,
        timeout_seconds=30,
        clock=lambda: now + timedelta(seconds=10),
        sleep=fake_sleep,
    )
    task = asyncio.create_task(controller.run())

    while not websocket.sent:
        await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert websocket.sent[0]["type"] == "PING"
    assert websocket.close_calls == []


@pytest.mark.asyncio
async def test_heartbeat_timeout_closes_connection() -> None:
    manager = ConnectionManager()
    registry = SessionRuntimeRegistry()
    websocket = FakeWebSocket()
    now = datetime(2026, 6, 28, 3, 10, tzinfo=UTC)
    await manager.register("session-1", websocket)
    await registry.get_or_create("session-1", connected_at=now - timedelta(seconds=31))

    async def fake_sleep(_: float) -> None:
        return

    controller = HeartbeatController(
        session_id="session-1",
        websocket=websocket,
        connection_manager=manager,
        runtime_registry=registry,
        interval_seconds=10,
        timeout_seconds=30,
        clock=lambda: now,
        sleep=fake_sleep,
    )

    await controller.run()

    assert websocket.sent == []
    assert websocket.close_calls == [(4008, "HEARTBEAT_TIMEOUT")]


@pytest.mark.asyncio
async def test_start_is_idempotent_and_stop_cancels_task() -> None:
    manager = ConnectionManager()
    registry = SessionRuntimeRegistry()
    websocket = FakeWebSocket()
    now = datetime(2026, 6, 28, 3, 10, tzinfo=UTC)
    await manager.register("session-1", websocket)
    await registry.get_or_create("session-1", connected_at=now)
    blocker = asyncio.Event()

    async def fake_sleep(_: float) -> None:
        await blocker.wait()

    controller = HeartbeatController(
        session_id="session-1",
        websocket=websocket,
        connection_manager=manager,
        runtime_registry=registry,
        interval_seconds=10,
        timeout_seconds=30,
        clock=lambda: now,
        sleep=fake_sleep,
    )

    controller.start()
    first_task = controller.task
    controller.start()

    assert controller.task is first_task
    assert first_task is not None

    await controller.stop()

    assert first_task.cancelled()
