from datetime import UTC, datetime

import pytest

from app.realtime.protocol import (
    ProtocolError,
    make_error_message,
    make_ping_message,
    make_session_ready_message,
    parse_client_text_message,
)


def test_session_ready_message_uses_camel_case_and_utc_z() -> None:
    message = make_session_ready_message(
        session_id="67371b45-204c-4d87-b8f7-8a334229a41e",
        model_version="vit-dms-1.0.0",
        policy_version="risk-policy-1.0.0",
        recommended_frame_fps=5,
        location_interval_ms=1000,
        heartbeat_interval_ms=10000,
        occurred_at=datetime(2026, 6, 28, 3, 10, tzinfo=UTC),
    )

    assert message == {
        "type": "SESSION_READY",
        "occurredAt": "2026-06-28T03:10:00.000000Z",
        "payload": {
            "sessionId": "67371b45-204c-4d87-b8f7-8a334229a41e",
            "modelVersion": "vit-dms-1.0.0",
            "policyVersion": "risk-policy-1.0.0",
            "recommendedFrameFps": 5,
            "locationIntervalMs": 1000,
            "heartbeatIntervalMs": 10000,
        },
    }


def test_ping_message_uses_utc_z() -> None:
    message = make_ping_message(occurred_at=datetime(2026, 6, 28, 3, 10, 10, tzinfo=UTC))

    assert message == {
        "type": "PING",
        "occurredAt": "2026-06-28T03:10:10.000000Z",
        "payload": {},
    }


def test_error_message_uses_camel_case_payload() -> None:
    message = make_error_message(
        code="WEBSOCKET_PROTOCOL_ERROR",
        message="현재 지원하지 않는 WebSocket 메시지입니다.",
        recoverable=False,
        occurred_at=datetime(2026, 6, 28, 3, 15, 6, tzinfo=UTC),
    )

    assert message == {
        "type": "ERROR",
        "occurredAt": "2026-06-28T03:15:06.000000Z",
        "payload": {
            "code": "WEBSOCKET_PROTOCOL_ERROR",
            "message": "현재 지원하지 않는 WebSocket 메시지입니다.",
            "recoverable": False,
        },
    }


def test_parse_client_pong_message_normalizes_timezone_to_utc() -> None:
    envelope = parse_client_text_message(
        """
        {
          "type": "PONG",
          "occurredAt": "2026-06-28T12:10:10.100000+09:00",
          "payload": {}
        }
        """
    )

    assert envelope.type == "PONG"
    assert envelope.occurred_at == datetime(2026, 6, 28, 3, 10, 10, 100000, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw_message",
    [
        "not-json",
        '{"occurredAt":"2026-06-28T03:10:10Z","payload":{}}',
        '{"type":"PONG","payload":{}}',
        '{"type":"PONG","occurredAt":"2026-06-28T03:10:10","payload":{}}',
        '{"type":"PONG","occurredAt":"2026-06-28T03:10:10Z","payload":[]}',
        '{"type":"PONG","occurredAt":"2026-06-28T03:10:10Z","payload":{},"extra":true}',
        '{"type":"LOCATION_UPDATE","occurredAt":"2026-06-28T03:10:10Z","payload":{}}',
    ],
)
def test_parse_client_message_rejects_invalid_envelopes(raw_message: str) -> None:
    with pytest.raises(ProtocolError):
        parse_client_text_message(raw_message)
