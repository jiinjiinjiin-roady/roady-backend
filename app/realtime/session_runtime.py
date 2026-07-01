from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from app.core.enums import DrivingState
from app.core.time import utc_now_for_api_response


@dataclass(slots=True)
class SessionRuntime:
    session_id: str
    connected_at: datetime
    last_message_at: datetime
    last_heartbeat_at: datetime
    current_latitude: float | None = None
    current_longitude: float | None = None
    current_speed_kph: float | None = None
    driving_state: DrivingState = DrivingState.UNKNOWN
    last_location_persisted_at: datetime | None = None
    active_behavior_event_id: str | None = None
    current_intervention_id: str | None = None
    active_conversation_id: str | None = None


class SessionRuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[str, SessionRuntime] = {}
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._runtimes)

    async def get_or_create(
        self,
        session_id: str,
        *,
        connected_at: datetime | None = None,
    ) -> SessionRuntime:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is not None:
                return runtime

            now = connected_at or utc_now_for_api_response()
            runtime = SessionRuntime(
                session_id=session_id,
                connected_at=now,
                last_message_at=now,
                last_heartbeat_at=now,
            )
            self._runtimes[session_id] = runtime
            return runtime

    async def get(self, session_id: str) -> SessionRuntime | None:
        async with self._lock:
            return self._runtimes.get(session_id)

    async def touch_message(self, session_id: str, occurred_at: datetime) -> SessionRuntime | None:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return None
            runtime.last_message_at = occurred_at
            return runtime

    async def touch_heartbeat(
        self,
        session_id: str,
        occurred_at: datetime,
    ) -> SessionRuntime | None:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return None
            runtime.last_message_at = occurred_at
            runtime.last_heartbeat_at = occurred_at
            return runtime

    async def remove(self, session_id: str) -> bool:
        async with self._lock:
            return self._runtimes.pop(session_id, None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._runtimes.clear()
