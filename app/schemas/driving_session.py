from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import field_serializer, field_validator
from pydantic_core import PydanticCustomError

from app.core.enums import DrivingSessionStatus, SessionEndReason
from app.core.error_codes import ErrorCode
from app.core.time import format_utc_datetime
from app.schemas.base import ApiBaseModel, ApiRequestModel
from app.utils.uuid import normalize_uuid_string

INVALID_PROFILE_ID_MESSAGE = "Profile ID format is invalid."
INVALID_START_LOCATION_MESSAGE = "Start location is invalid."
INVALID_DESTINATION_MESSAGE = "Destination is invalid."
INVALID_END_LOCATION_MESSAGE = "End location is invalid."
INVALID_END_REASON_MESSAGE = "End reason is invalid."


def _raise_validation_error(error_code: ErrorCode, message: str) -> None:
    raise PydanticCustomError(error_code.value, message)


def _validate_coordinate_number(value: object, *, error_code: ErrorCode, message: str) -> float:
    if isinstance(value, bool):
        _raise_validation_error(error_code, message)

    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        _raise_validation_error(error_code, message)

    if not math.isfinite(coordinate):
        _raise_validation_error(error_code, message)

    return coordinate


def _validate_latitude(value: object, *, error_code: ErrorCode, message: str) -> float:
    latitude = _validate_coordinate_number(value, error_code=error_code, message=message)
    if latitude < -90 or latitude > 90:
        _raise_validation_error(error_code, message)
    return latitude


def _validate_longitude(value: object, *, error_code: ErrorCode, message: str) -> float:
    longitude = _validate_coordinate_number(value, error_code=error_code, message=message)
    if longitude < -180 or longitude > 180:
        _raise_validation_error(error_code, message)
    return longitude


def _validate_optional_text(
    value: object,
    *,
    max_length: int,
    error_code: ErrorCode,
    message: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        _raise_validation_error(error_code, message)

    normalized = value.strip()
    if not normalized:
        return None

    if len(normalized) > max_length:
        _raise_validation_error(error_code, message)

    return normalized


def _validate_required_text(
    value: object,
    *,
    max_length: int,
    error_code: ErrorCode,
    message: str,
) -> str:
    if not isinstance(value, str):
        _raise_validation_error(error_code, message)

    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        _raise_validation_error(error_code, message)

    return normalized


class CoordinateRequest(ApiRequestModel):
    latitude: float
    longitude: float

    @field_validator("latitude", mode="before")
    @classmethod
    def validate_latitude(cls, value: object) -> float:
        return _validate_latitude(
            value,
            error_code=ErrorCode.INVALID_START_LOCATION,
            message=INVALID_START_LOCATION_MESSAGE,
        )

    @field_validator("longitude", mode="before")
    @classmethod
    def validate_longitude(cls, value: object) -> float:
        return _validate_longitude(
            value,
            error_code=ErrorCode.INVALID_START_LOCATION,
            message=INVALID_START_LOCATION_MESSAGE,
        )


class DestinationRequest(ApiRequestModel):
    provider_place_id: str | None = None
    name: str
    latitude: float
    longitude: float

    @field_validator("provider_place_id", mode="before")
    @classmethod
    def validate_provider_place_id(cls, value: object) -> str | None:
        return _validate_optional_text(
            value,
            max_length=255,
            error_code=ErrorCode.INVALID_DESTINATION,
            message=INVALID_DESTINATION_MESSAGE,
        )

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _validate_required_text(
            value,
            max_length=200,
            error_code=ErrorCode.INVALID_DESTINATION,
            message=INVALID_DESTINATION_MESSAGE,
        )

    @field_validator("latitude", mode="before")
    @classmethod
    def validate_latitude(cls, value: object) -> float:
        return _validate_latitude(
            value,
            error_code=ErrorCode.INVALID_DESTINATION,
            message=INVALID_DESTINATION_MESSAGE,
        )

    @field_validator("longitude", mode="before")
    @classmethod
    def validate_longitude(cls, value: object) -> float:
        return _validate_longitude(
            value,
            error_code=ErrorCode.INVALID_DESTINATION,
            message=INVALID_DESTINATION_MESSAGE,
        )


class DrivingSessionStartRequest(ApiRequestModel):
    profile_id: str
    start_location: CoordinateRequest
    destination: DestinationRequest | None = None

    @field_validator("profile_id", mode="before")
    @classmethod
    def validate_profile_id(cls, value: object) -> str:
        try:
            return normalize_uuid_string(str(value))
        except (TypeError, ValueError) as exc:
            raise PydanticCustomError(
                ErrorCode.INVALID_PROFILE_ID.value,
                INVALID_PROFILE_ID_MESSAGE,
            ) from exc

    def to_model_data(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "start_latitude": self.start_location.latitude,
            "start_longitude": self.start_location.longitude,
            "destination_name": None if self.destination is None else self.destination.name,
            "destination_place_id": (
                None if self.destination is None else self.destination.provider_place_id
            ),
        }


class DrivingSessionEndRequest(ApiRequestModel):
    end_reason: str
    end_location: CoordinateRequest | None = None

    @field_validator("end_reason", mode="before")
    @classmethod
    def validate_end_reason(cls, value: object) -> str:
        if not isinstance(value, str) or value not in {item.value for item in SessionEndReason}:
            _raise_validation_error(ErrorCode.INVALID_END_REASON, INVALID_END_REASON_MESSAGE)
        return value


class CoordinateResponse(ApiBaseModel):
    latitude: float
    longitude: float


class SessionStartDestinationResponse(ApiBaseModel):
    provider_place_id: str | None
    name: str


class DrivingSessionStartResponse(ApiBaseModel):
    id: str
    profile_id: str
    status: str
    started_at: datetime
    start_location: CoordinateResponse
    destination: SessionStartDestinationResponse | None
    model_version: str
    policy_version: str
    web_socket_url: str

    @field_serializer("started_at")
    def serialize_started_at(self, value: datetime) -> str:
        return format_utc_datetime(value)


class ActiveDrivingSessionResponse(ApiBaseModel):
    id: str
    profile_id: str
    status: str
    started_at: datetime
    destination_name: str | None
    model_version: str
    policy_version: str
    web_socket_url: str

    @field_serializer("started_at")
    def serialize_started_at(self, value: datetime) -> str:
        return format_utc_datetime(value)


class DrivingSessionSummaryResponse(ApiBaseModel):
    behavior_event_count: int
    intervention_count: int
    corrected_behavior_count: int
    behavior_correction_rate: float
    average_response_latency_ms: float | None = None


class DrivingSessionDetailResponse(ApiBaseModel):
    id: str
    profile_id: str
    status: str
    end_reason: str | None
    started_at: datetime
    ended_at: datetime | None
    start_location: CoordinateResponse | None
    end_location: CoordinateResponse | None
    destination_name: str | None
    distance_meters: int
    duration_seconds: int
    average_speed_kph: float | None
    safety_score: int | None
    model_version: str
    policy_version: str
    summary: DrivingSessionSummaryResponse

    @field_serializer("started_at", "ended_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return None if value is None else format_utc_datetime(value)


class DrivingSessionEndResponse(DrivingSessionDetailResponse):
    pass


class DrivingSessionHistoryItemResponse(ApiBaseModel):
    id: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    destination_name: str | None
    distance_meters: int
    duration_seconds: int
    average_speed_kph: float | None
    safety_score: int | None
    behavior_event_count: int

    @field_serializer("started_at", "ended_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return None if value is None else format_utc_datetime(value)


class DrivingSessionHistoryResponse(ApiBaseModel):
    items: list[DrivingSessionHistoryItemResponse]
    page: int
    size: int
    total: int
    total_pages: int

    @classmethod
    def from_items(
        cls,
        *,
        items: list[DrivingSessionHistoryItemResponse],
        page: int,
        size: int,
        total: int,
    ) -> DrivingSessionHistoryResponse:
        total_pages = 0 if total == 0 else (total + size - 1) // size
        return cls(items=items, page=page, size=size, total=total, total_pages=total_pages)


class DriverResponseTimelineItemResponse(ApiBaseModel):
    response_type: str
    behavior_corrected: bool | None
    response_latency_ms: int | None
    responded_at: datetime

    @field_serializer("responded_at")
    def serialize_responded_at(self, value: datetime) -> str:
        return format_utc_datetime(value)


class InterventionTimelineItemResponse(ApiBaseModel):
    intervention_id: str
    level: int
    intervention_type: str
    ui_text: str
    speech_text: str | None
    status: str
    responses: list[DriverResponseTimelineItemResponse]


class BehaviorEventTimelineItemResponse(ApiBaseModel):
    event_id: str
    behavior_type: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    average_confidence: float
    maximum_confidence: float
    risk_level: int
    driving_state: str
    speed_kph: float | None
    resolution_reason: str | None
    interventions: list[InterventionTimelineItemResponse]

    @field_serializer("started_at", "ended_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return None if value is None else format_utc_datetime(value)


class DrivingSessionTimelineResponse(ApiBaseModel):
    session_id: str
    events: list[BehaviorEventTimelineItemResponse]


class LocationSampleResponse(ApiBaseModel):
    latitude: float
    longitude: float
    speed_kph: float | None
    driving_state: str
    accuracy_meters: float | None
    source: str
    recorded_at: datetime

    @field_serializer("recorded_at")
    def serialize_recorded_at(self, value: datetime) -> str:
        return format_utc_datetime(value)


class DrivingSessionLocationsResponse(ApiBaseModel):
    session_id: str
    samples: list[LocationSampleResponse]
    count: int


SESSION_STATUS_VALUES = {item.value for item in DrivingSessionStatus}
