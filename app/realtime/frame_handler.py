from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from fastapi import WebSocket

from app.realtime.connection_manager import ConnectionManager
from app.realtime.protocol import FrameMetaMessage
from app.realtime.session_runtime import AcceptedFrame, FrameMetadata, SessionRuntimeRegistry


class FrameIngressStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    TOO_LARGE = "TOO_LARGE"
    INVALID_JPEG = "INVALID_JPEG"
    DUPLICATE = "DUPLICATE"
    NOT_CURRENT_CONNECTION = "NOT_CURRENT_CONNECTION"
    RUNTIME_NOT_FOUND = "RUNTIME_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class FrameIngressResult:
    status: FrameIngressStatus
    dropped_count: int = 0


class FrameIngressService:
    def __init__(
        self,
        *,
        connection_manager: ConnectionManager,
        runtime_registry: SessionRuntimeRegistry,
        max_frame_bytes: int,
    ) -> None:
        self.connection_manager = connection_manager
        self.runtime_registry = runtime_registry
        self.max_frame_bytes = max_frame_bytes

    async def handle(
        self,
        *,
        session_id: str,
        websocket: WebSocket,
        message: FrameMetaMessage,
        frame_bytes: bytes,
        received_at: datetime,
    ) -> FrameIngressResult:
        if len(frame_bytes) > self.max_frame_bytes:
            return FrameIngressResult(status=FrameIngressStatus.TOO_LARGE)

        if not _has_jpeg_markers(frame_bytes):
            return FrameIngressResult(status=FrameIngressStatus.INVALID_JPEG)

        if not await self.connection_manager.is_current(session_id, websocket):
            return FrameIngressResult(status=FrameIngressStatus.NOT_CURRENT_CONNECTION)

        result = await self.runtime_registry.accept_frame(
            session_id,
            AcceptedFrame(
                metadata=FrameMetadata(
                    frame_id=message.payload.frame_id,
                    request_id=str(message.request_id),
                    occurred_at=message.occurred_at,
                    format=message.payload.format,
                    width=message.payload.width,
                    height=message.payload.height,
                    captured_at=message.payload.captured_at,
                ),
                jpeg_bytes=frame_bytes,
                received_at=received_at,
            ),
        )
        return FrameIngressResult(
            status=FrameIngressStatus(result.status.value),
            dropped_count=result.dropped_count,
        )


def _has_jpeg_markers(frame_bytes: bytes) -> bool:
    return len(frame_bytes) >= 4 and frame_bytes.startswith(b"\xff\xd8") and frame_bytes.endswith(
        b"\xff\xd9"
    )
