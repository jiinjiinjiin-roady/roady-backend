import asyncio
from datetime import UTC, datetime

import pytest

from app.realtime.frame_pairing import FramePairingController
from app.realtime.protocol import FrameMetaMessage, parse_client_text_message


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
async def test_claim_binary_returns_pending_meta_and_cancels_timeout() -> None:
    sleep_gate = asyncio.Event()
    timed_out: list[str] = []

    async def gated_sleep(_: float) -> None:
        await sleep_gate.wait()

    async def on_timeout(message: FrameMetaMessage) -> None:
        timed_out.append(message.payload.frame_id)

    controller = FramePairingController(
        timeout_seconds=1,
        on_timeout=on_timeout,
        sleep=gated_sleep,
    )

    await controller.replace_pending(frame_meta("frame-1"))
    claimed = await controller.claim_binary()
    sleep_gate.set()
    await asyncio.sleep(0)

    assert claimed is not None
    assert claimed.payload.frame_id == "frame-1"
    assert timed_out == []
    assert await controller.has_pending() is False


@pytest.mark.asyncio
async def test_timeout_clears_pending_and_emits_once() -> None:
    timed_out: list[str] = []

    async def immediate_sleep(_: float) -> None:
        return None

    async def on_timeout(message: FrameMetaMessage) -> None:
        timed_out.append(message.payload.frame_id)

    controller = FramePairingController(
        timeout_seconds=1,
        on_timeout=on_timeout,
        sleep=immediate_sleep,
    )

    await controller.replace_pending(frame_meta("frame-1"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert timed_out == ["frame-1"]
    assert await controller.claim_binary() is None


@pytest.mark.asyncio
async def test_replace_pending_returns_old_meta() -> None:
    async def on_timeout(_: FrameMetaMessage) -> None:
        raise AssertionError("timeout should have been cancelled")

    controller = FramePairingController(timeout_seconds=60, on_timeout=on_timeout)

    old = await controller.replace_pending(frame_meta("frame-1"))
    replaced = await controller.replace_pending(frame_meta("frame-2"))
    claimed = await controller.claim_binary()

    assert old is None
    assert replaced is not None
    assert replaced.payload.frame_id == "frame-1"
    assert claimed is not None
    assert claimed.payload.frame_id == "frame-2"


@pytest.mark.asyncio
async def test_close_clears_pending_without_timeout() -> None:
    timed_out: list[datetime] = []

    async def on_timeout(_: FrameMetaMessage) -> None:
        timed_out.append(datetime.now(UTC))

    controller = FramePairingController(timeout_seconds=60, on_timeout=on_timeout)

    await controller.replace_pending(frame_meta("frame-1"))
    await controller.close()

    assert timed_out == []
    assert await controller.has_pending() is False
