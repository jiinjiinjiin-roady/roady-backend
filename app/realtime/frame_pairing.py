from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.realtime.protocol import FrameMetaMessage

TimeoutCallback = Callable[[FrameMetaMessage], Awaitable[None]]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(slots=True)
class _PendingFrameMeta:
    message: FrameMetaMessage
    generation: int


class FramePairingController:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        on_timeout: TimeoutCallback,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.on_timeout = on_timeout
        self.sleep = sleep
        self._lock = asyncio.Lock()
        self._pending: _PendingFrameMeta | None = None
        self._timeout_task: asyncio.Task[None] | None = None
        self._generation = 0

    async def has_pending(self) -> bool:
        async with self._lock:
            return self._pending is not None

    async def replace_pending(self, message: FrameMetaMessage) -> FrameMetaMessage | None:
        async with self._lock:
            old_pending = self._pending
            old_task = self._timeout_task
            self._generation += 1
            generation = self._generation
            self._pending = _PendingFrameMeta(message=message, generation=generation)
            self._timeout_task = asyncio.create_task(self._run_timeout(generation))
            if old_task is not None:
                old_task.cancel()

        await _await_cancelled_task(old_task)
        return old_pending.message if old_pending is not None else None

    async def drop_pending(self) -> FrameMetaMessage | None:
        async with self._lock:
            old_pending = self._pending
            old_task = self._timeout_task
            self._generation += 1
            self._pending = None
            self._timeout_task = None
            if old_task is not None:
                old_task.cancel()

        await _await_cancelled_task(old_task)
        return old_pending.message if old_pending is not None else None

    async def claim_binary(self) -> FrameMetaMessage | None:
        return await self.drop_pending()

    async def close(self) -> None:
        await self.drop_pending()

    async def _run_timeout(self, generation: int) -> None:
        try:
            await self.sleep(self.timeout_seconds)
            async with self._lock:
                if self._pending is None or self._pending.generation != generation:
                    return

                message = self._pending.message
                self._generation += 1
                self._pending = None
                self._timeout_task = None

            await self.on_timeout(message)
        except asyncio.CancelledError:
            raise


async def _await_cancelled_task(task: asyncio.Task[None] | None) -> None:
    if task is None or task.done():
        return

    try:
        await task
    except asyncio.CancelledError:
        pass
