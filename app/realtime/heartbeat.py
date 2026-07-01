from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import WebSocket

from app.core.time import utc_now_for_api_response
from app.realtime.connection_manager import ConnectionManager
from app.realtime.protocol import WebSocketCloseCode, make_ping_message
from app.realtime.session_runtime import SessionRuntimeRegistry

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


class HeartbeatController:
    def __init__(
        self,
        *,
        session_id: str,
        websocket: WebSocket,
        connection_manager: ConnectionManager,
        runtime_registry: SessionRuntimeRegistry,
        interval_seconds: float,
        timeout_seconds: float,
        clock: Clock = utc_now_for_api_response,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.session_id = session_id
        self.websocket = websocket
        self.connection_manager = connection_manager
        self.runtime_registry = runtime_registry
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self.sleep = sleep
        self._task: asyncio.Task[None] | None = None

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def run(self) -> None:
        try:
            while True:
                await self.sleep(self.interval_seconds)
                if not await self.connection_manager.is_current(self.session_id, self.websocket):
                    return

                runtime = await self.runtime_registry.get(self.session_id)
                if runtime is None:
                    return

                now = self.clock()
                elapsed = (now - runtime.last_heartbeat_at).total_seconds()
                if elapsed > self.timeout_seconds:
                    await self.websocket.close(
                        code=WebSocketCloseCode.HEARTBEAT_TIMEOUT,
                        reason="HEARTBEAT_TIMEOUT",
                    )
                    return

                await self.connection_manager.send_json_to_current(
                    self.session_id,
                    self.websocket,
                    make_ping_message(occurred_at=now),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Heartbeat task failed session_id=%s", self.session_id)
            try:
                await self.websocket.close(
                    code=WebSocketCloseCode.INTERNAL_ERROR,
                    reason="INTERNAL_WEBSOCKET_ERROR",
                )
            except Exception:
                logger.exception("Failed to close WebSocket after heartbeat failure")
