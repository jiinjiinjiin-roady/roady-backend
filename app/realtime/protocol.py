from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, ValidationError, field_serializer, field_validator

from app.core.time import ensure_utc_datetime, format_utc_datetime, utc_now_for_api_response
from app.schemas.base import ApiBaseModel, to_camel


class WebSocketCloseCode:
    SESSION_CONNECTION_REPLACED = 4001
    HEARTBEAT_TIMEOUT = 4008
    POLICY_VIOLATION = 1008
    INTERNAL_ERROR = 1011
    SERVICE_RESTART = 1012


class ServerMessageType(StrEnum):
    SESSION_READY = "SESSION_READY"
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"


class ClientMessageType(StrEnum):
    PONG = "PONG"


class ProtocolError(Exception):
    pass


class StrictApiModel(ApiBaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class SessionReadyPayload(StrictApiModel):
    session_id: str
    model_version: str
    policy_version: str
    recommended_frame_fps: int
    location_interval_ms: int
    heartbeat_interval_ms: int


class ErrorPayload(StrictApiModel):
    code: str
    message: str
    recoverable: bool


class ServerEnvelope(StrictApiModel):
    type: ServerMessageType
    occurred_at: datetime
    payload: dict[str, Any]

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        return format_utc_datetime(value)

    def to_message(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class ClientEnvelope(StrictApiModel):
    type: ClientMessageType
    occurred_at: datetime
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurredAt must include timezone information.")
        return ensure_utc_datetime(value)


def parse_client_text_message(raw_text: str) -> ClientEnvelope:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("Invalid JSON WebSocket message.") from exc

    try:
        return ClientEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise ProtocolError("Invalid WebSocket message envelope.") from exc


def make_session_ready_message(
    *,
    session_id: str,
    model_version: str,
    policy_version: str,
    recommended_frame_fps: int,
    location_interval_ms: int,
    heartbeat_interval_ms: int,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    payload = SessionReadyPayload(
        session_id=session_id,
        model_version=model_version,
        policy_version=policy_version,
        recommended_frame_fps=recommended_frame_fps,
        location_interval_ms=location_interval_ms,
        heartbeat_interval_ms=heartbeat_interval_ms,
    )
    return _server_message(
        ServerMessageType.SESSION_READY,
        payload.model_dump(by_alias=True),
        occurred_at=occurred_at,
    )


def make_ping_message(*, occurred_at: datetime | None = None) -> dict[str, Any]:
    return _server_message(ServerMessageType.PING, {}, occurred_at=occurred_at)


def make_pong_message(*, occurred_at: datetime | None = None) -> dict[str, Any]:
    return _server_message(ServerMessageType.PONG, {}, occurred_at=occurred_at)


def make_error_message(
    *,
    code: str,
    message: str,
    recoverable: bool,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    payload = ErrorPayload(code=code, message=message, recoverable=recoverable)
    return _server_message(
        ServerMessageType.ERROR,
        payload.model_dump(by_alias=True),
        occurred_at=occurred_at,
    )


def _server_message(
    message_type: ServerMessageType,
    payload: dict[str, Any],
    *,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    envelope = ServerEnvelope(
        type=message_type,
        occurred_at=occurred_at or utc_now_for_api_response(),
        payload=payload,
    )
    return envelope.to_message()
