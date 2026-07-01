from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.enums import DrivingState, LocationSource
from app.core.time import utc_now_for_api_response


@dataclass(frozen=True, slots=True)
class FrameMetadata:
    frame_id: str
    request_id: str
    occurred_at: datetime
    format: str
    width: int
    height: int
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class AcceptedFrame:
    metadata: FrameMetadata
    jpeg_bytes: bytes
    received_at: datetime


@dataclass(frozen=True, slots=True)
class LatestFrameQueuePutResult:
    dropped_frame: AcceptedFrame | None
    queue_size: int


class LatestFrameQueue:
    def __init__(self, max_size: int) -> None:
        if max_size not in {1, 2}:
            raise ValueError("LatestFrameQueue max_size must be 1 or 2.")
        self.max_size = max_size
        self._items: deque[AcceptedFrame] = deque()

    def put_latest(self, frame: AcceptedFrame) -> LatestFrameQueuePutResult:
        dropped_frame = None
        if len(self._items) >= self.max_size:
            dropped_frame = self._items.popleft()
        self._items.append(frame)
        return LatestFrameQueuePutResult(
            dropped_frame=dropped_frame,
            queue_size=len(self._items),
        )

    def get(self) -> AcceptedFrame | None:
        if not self._items:
            return None
        return self._items.popleft()

    def qsize(self) -> int:
        return len(self._items)

    def list_frames(self) -> Sequence[AcceptedFrame]:
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()


class FrameAcceptStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    RUNTIME_NOT_FOUND = "RUNTIME_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class FrameAcceptResult:
    status: FrameAcceptStatus
    dropped_count: int = 0


@dataclass(slots=True)
class SessionRuntime:
    session_id: str
    connected_at: datetime
    last_message_at: datetime
    last_heartbeat_at: datetime
    current_latitude: float | None = None
    current_longitude: float | None = None
    current_speed_kph: float | None = None
    current_accuracy_meters: float | None = None
    current_location_source: LocationSource | None = None
    driving_state: DrivingState = DrivingState.UNKNOWN
    last_location_occurred_at: datetime | None = None
    last_location_persisted_at: datetime | None = None
    last_location_persisted_monotonic: float | None = None
    latest_frame_queue: LatestFrameQueue | None = None
    recent_frame_ids: OrderedDict[str, None] | None = None
    frame_queue_max_size: int = 2
    frame_recent_id_cache_size: int = 256
    last_accepted_frame_id: str | None = None
    last_accepted_captured_at: datetime | None = None
    accepted_frame_count: int = 0
    dropped_frame_count: int = 0
    active_behavior_event_id: str | None = None
    current_intervention_id: str | None = None
    active_conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class LocationRuntimeUpdate:
    latitude: float
    longitude: float
    speed_kph: float | None
    accuracy_meters: float | None
    source: LocationSource
    driving_state: DrivingState
    occurred_at: datetime
    received_at: datetime


@dataclass(frozen=True, slots=True)
class LocationRuntimeSnapshot:
    session_id: str
    current_latitude: float | None
    current_longitude: float | None
    current_speed_kph: float | None
    current_accuracy_meters: float | None
    current_location_source: LocationSource | None
    driving_state: DrivingState
    last_location_occurred_at: datetime | None
    last_location_persisted_at: datetime | None
    last_location_persisted_monotonic: float | None


class LocationRuntimeApplyStatus(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class LocationRuntimeApplyResult:
    status: LocationRuntimeApplyStatus
    snapshot: LocationRuntimeSnapshot | None


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
        frame_queue_max_size: int = 2,
        frame_recent_id_cache_size: int = 256,
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
                latest_frame_queue=LatestFrameQueue(frame_queue_max_size),
                recent_frame_ids=OrderedDict(),
                frame_queue_max_size=frame_queue_max_size,
                frame_recent_id_cache_size=frame_recent_id_cache_size,
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

    async def get_location_snapshot(self, session_id: str) -> LocationRuntimeSnapshot | None:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return None
            return self._snapshot(runtime)

    async def apply_location_update(
        self,
        session_id: str,
        update: LocationRuntimeUpdate,
    ) -> LocationRuntimeApplyResult:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return LocationRuntimeApplyResult(
                    status=LocationRuntimeApplyStatus.NOT_FOUND,
                    snapshot=None,
                )

            if runtime.last_location_occurred_at is not None:
                if update.occurred_at < runtime.last_location_occurred_at:
                    return LocationRuntimeApplyResult(
                        status=LocationRuntimeApplyStatus.STALE,
                        snapshot=self._snapshot(runtime),
                    )
                if update.occurred_at == runtime.last_location_occurred_at:
                    return LocationRuntimeApplyResult(
                        status=LocationRuntimeApplyStatus.DUPLICATE,
                        snapshot=self._snapshot(runtime),
                    )

            runtime.current_latitude = update.latitude
            runtime.current_longitude = update.longitude
            runtime.current_speed_kph = update.speed_kph
            runtime.current_accuracy_meters = update.accuracy_meters
            runtime.current_location_source = update.source
            runtime.driving_state = update.driving_state
            runtime.last_location_occurred_at = update.occurred_at
            runtime.last_message_at = update.received_at
            return LocationRuntimeApplyResult(
                status=LocationRuntimeApplyStatus.APPLIED,
                snapshot=self._snapshot(runtime),
            )

    async def mark_location_persisted(
        self,
        session_id: str,
        *,
        occurred_at: datetime,
        monotonic_value: float,
    ) -> LocationRuntimeSnapshot | None:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return None
            runtime.last_location_persisted_at = occurred_at
            runtime.last_location_persisted_monotonic = monotonic_value
            return self._snapshot(runtime)

    async def reset_frame_state(
        self,
        session_id: str,
        *,
        frame_queue_max_size: int,
        frame_recent_id_cache_size: int,
    ) -> bool:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return False

            runtime.latest_frame_queue = LatestFrameQueue(frame_queue_max_size)
            runtime.recent_frame_ids = OrderedDict()
            runtime.frame_queue_max_size = frame_queue_max_size
            runtime.frame_recent_id_cache_size = frame_recent_id_cache_size
            runtime.last_accepted_frame_id = None
            runtime.last_accepted_captured_at = None
            runtime.accepted_frame_count = 0
            runtime.dropped_frame_count = 0
            return True

    async def accept_frame(self, session_id: str, frame: AcceptedFrame) -> FrameAcceptResult:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None:
                return FrameAcceptResult(status=FrameAcceptStatus.RUNTIME_NOT_FOUND)

            if runtime.latest_frame_queue is None:
                runtime.latest_frame_queue = LatestFrameQueue(runtime.frame_queue_max_size)
            if runtime.recent_frame_ids is None:
                runtime.recent_frame_ids = OrderedDict()

            if frame.metadata.frame_id in runtime.recent_frame_ids:
                return FrameAcceptResult(status=FrameAcceptStatus.DUPLICATE)

            queue_result = runtime.latest_frame_queue.put_latest(frame)
            runtime.recent_frame_ids[frame.metadata.frame_id] = None
            while len(runtime.recent_frame_ids) > runtime.frame_recent_id_cache_size:
                runtime.recent_frame_ids.popitem(last=False)

            runtime.accepted_frame_count += 1
            runtime.last_accepted_frame_id = frame.metadata.frame_id
            runtime.last_accepted_captured_at = frame.metadata.captured_at
            dropped_count = 1 if queue_result.dropped_frame is not None else 0
            runtime.dropped_frame_count += dropped_count
            return FrameAcceptResult(
                status=FrameAcceptStatus.ACCEPTED,
                dropped_count=dropped_count,
            )

    async def get_latest_frame_queue_snapshot(self, session_id: str) -> Sequence[AcceptedFrame]:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None or runtime.latest_frame_queue is None:
                return ()
            return runtime.latest_frame_queue.list_frames()

    async def get_next_frame(self, session_id: str) -> AcceptedFrame | None:
        async with self._lock:
            runtime = self._runtimes.get(session_id)
            if runtime is None or runtime.latest_frame_queue is None:
                return None
            return runtime.latest_frame_queue.get()

    async def remove(self, session_id: str) -> bool:
        async with self._lock:
            return self._runtimes.pop(session_id, None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._runtimes.clear()

    @staticmethod
    def _snapshot(runtime: SessionRuntime) -> LocationRuntimeSnapshot:
        return LocationRuntimeSnapshot(
            session_id=runtime.session_id,
            current_latitude=runtime.current_latitude,
            current_longitude=runtime.current_longitude,
            current_speed_kph=runtime.current_speed_kph,
            current_accuracy_meters=runtime.current_accuracy_meters,
            current_location_source=runtime.current_location_source,
            driving_state=runtime.driving_state,
            last_location_occurred_at=runtime.last_location_occurred_at,
            last_location_persisted_at=runtime.last_location_persisted_at,
            last_location_persisted_monotonic=runtime.last_location_persisted_monotonic,
        )
