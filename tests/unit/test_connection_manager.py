import asyncio
from typing import Any

import pytest
from starlette.websockets import WebSocketState

from app.realtime.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.sent: list[dict[str, Any]] = []
        self.close_calls: list[tuple[int, str]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        await asyncio.sleep(0)
        self.sent.append(message)

    async def close(self, *, code: int, reason: str) -> None:
        self.application_state = WebSocketState.DISCONNECTED
        self.close_calls.append((code, reason))


@pytest.mark.asyncio
async def test_register_get_send_disconnect_and_close() -> None:
    manager = ConnectionManager()
    websocket = FakeWebSocket()

    previous = await manager.register("session-1", websocket)
    assert previous is None
    assert manager.active_count == 1
    assert (await manager.get("session-1")).websocket is websocket

    sent = await manager.send_json("session-1", {"type": "PING"})
    assert sent is True
    assert websocket.sent == [{"type": "PING"}]

    removed = await manager.disconnect("session-1", websocket)
    assert removed is True
    assert manager.active_count == 0

    assert await manager.close("session-1", code=1000, reason="missing") is False


@pytest.mark.asyncio
async def test_duplicate_register_returns_previous_and_old_disconnect_does_not_remove_new() -> None:
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()

    assert await manager.register("session-1", first) is None
    previous = await manager.register("session-1", second)

    assert previous is not None
    assert previous.websocket is first
    assert manager.active_count == 1
    assert (await manager.get("session-1")).websocket is second

    assert await manager.disconnect("session-1", first) is False
    assert manager.active_count == 1
    assert (await manager.get("session-1")).websocket is second


@pytest.mark.asyncio
async def test_send_json_to_current_uses_object_identity() -> None:
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    await manager.register("session-1", first)

    assert await manager.send_json_to_current("session-1", second, {"type": "PING"}) is False
    assert first.sent == []
    assert second.sent == []

    assert await manager.send_json_to_current("session-1", first, {"type": "PING"}) is True
    assert first.sent == [{"type": "PING"}]


@pytest.mark.asyncio
async def test_close_and_close_all_remove_and_close_connections() -> None:
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    await manager.register("first", first)
    await manager.register("second", second)

    assert await manager.close("first", code=4008, reason="HEARTBEAT_TIMEOUT") is True
    assert first.close_calls == [(4008, "HEARTBEAT_TIMEOUT")]
    assert manager.active_count == 1

    await manager.close_all(code=1012, reason="SERVICE_RESTART")
    assert second.close_calls == [(1012, "SERVICE_RESTART")]
    assert manager.active_count == 0
