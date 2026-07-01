from datetime import UTC, datetime

import pytest

from app.realtime.frame_handler import FrameIngressService, FrameIngressStatus
from app.realtime.protocol import FrameMetaMessage, parse_client_text_message
from app.realtime.session_runtime import SessionRuntimeRegistry


class FakeConnectionManager:
    def __init__(self, *, current: bool = True) -> None:
        self.current = current

    async def is_current(self, session_id: str, websocket: object) -> bool:
        return self.current


def frame_meta(frame_id: str = "frame-1") -> FrameMetaMessage:
    message = parse_client_text_message(
        f"""
        {{
          "type": "FRAME_META",
          "requestId": "6a972e7b-2151-4997-acbd-19b01facb6b0",
          "occurredAt": "2026-06-28T03:10:10Z",
          "payload": {{
            "frameId": "{frame_id}",
            "format": "JPEG",
            "width": 640,
            "height": 360,
            "capturedAt": "2026-06-28T03:10:10Z"
          }}
        }}
        """
    )
    assert isinstance(message, FrameMetaMessage)
    return message


@pytest.mark.asyncio
async def test_frame_ingress_accepts_minimal_jpeg_and_enqueues() -> None:
    registry = SessionRuntimeRegistry()
    await registry.get_or_create("session-1")
    service = FrameIngressService(
        connection_manager=FakeConnectionManager(),
        runtime_registry=registry,
        max_frame_bytes=4,
    )

    result = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta(),
        frame_bytes=b"\xff\xd8\xff\xd9",
        received_at=datetime(2026, 6, 28, 3, 10, 11, tzinfo=UTC),
    )
    frames = await registry.get_latest_frame_queue_snapshot("session-1")

    assert result.status == FrameIngressStatus.ACCEPTED
    assert len(frames) == 1
    assert frames[0].metadata.frame_id == "frame-1"
    assert frames[0].jpeg_bytes == b"\xff\xd8\xff\xd9"


@pytest.mark.asyncio
async def test_frame_ingress_rejects_size_before_jpeg_validation() -> None:
    registry = SessionRuntimeRegistry()
    await registry.get_or_create("session-1")
    service = FrameIngressService(
        connection_manager=FakeConnectionManager(),
        runtime_registry=registry,
        max_frame_bytes=3,
    )

    result = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta(),
        frame_bytes=b"not-jpeg",
        received_at=datetime(2026, 6, 28, 3, 10, 11, tzinfo=UTC),
    )

    assert result.status == FrameIngressStatus.TOO_LARGE
    assert await registry.get_latest_frame_queue_snapshot("session-1") == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("frame_bytes", [b"", b"\x00\xd8\xff\xd9", b"\xff\xd8\xff\x00"])
async def test_frame_ingress_rejects_invalid_jpeg_without_caching_id(frame_bytes: bytes) -> None:
    registry = SessionRuntimeRegistry()
    await registry.get_or_create("session-1")
    service = FrameIngressService(
        connection_manager=FakeConnectionManager(),
        runtime_registry=registry,
        max_frame_bytes=64,
    )

    invalid = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta("frame-1"),
        frame_bytes=frame_bytes,
        received_at=datetime(2026, 6, 28, 3, 10, 11, tzinfo=UTC),
    )
    valid = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta("frame-1"),
        frame_bytes=b"\xff\xd8\xff\xd9",
        received_at=datetime(2026, 6, 28, 3, 10, 12, tzinfo=UTC),
    )

    assert invalid.status == FrameIngressStatus.INVALID_JPEG
    assert valid.status == FrameIngressStatus.ACCEPTED


@pytest.mark.asyncio
async def test_frame_ingress_rejects_duplicate_after_valid_frame() -> None:
    registry = SessionRuntimeRegistry()
    await registry.get_or_create("session-1")
    service = FrameIngressService(
        connection_manager=FakeConnectionManager(),
        runtime_registry=registry,
        max_frame_bytes=64,
    )

    first = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta("frame-1"),
        frame_bytes=b"\xff\xd8\xff\xd9",
        received_at=datetime(2026, 6, 28, 3, 10, 11, tzinfo=UTC),
    )
    duplicate = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta("frame-1"),
        frame_bytes=b"\xff\xd8\xff\xd9",
        received_at=datetime(2026, 6, 28, 3, 10, 12, tzinfo=UTC),
    )

    assert first.status == FrameIngressStatus.ACCEPTED
    assert duplicate.status == FrameIngressStatus.DUPLICATE
    assert len(await registry.get_latest_frame_queue_snapshot("session-1")) == 1


@pytest.mark.asyncio
async def test_frame_ingress_does_not_enqueue_for_replaced_connection() -> None:
    registry = SessionRuntimeRegistry()
    await registry.get_or_create("session-1")
    service = FrameIngressService(
        connection_manager=FakeConnectionManager(current=False),
        runtime_registry=registry,
        max_frame_bytes=64,
    )

    result = await service.handle(
        session_id="session-1",
        websocket=object(),
        message=frame_meta("frame-1"),
        frame_bytes=b"\xff\xd8\xff\xd9",
        received_at=datetime(2026, 6, 28, 3, 10, 11, tzinfo=UTC),
    )

    assert result.status == FrameIngressStatus.NOT_CURRENT_CONNECTION
    assert await registry.get_latest_frame_queue_snapshot("session-1") == ()
