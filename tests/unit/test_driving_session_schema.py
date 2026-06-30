from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.driving_session import (
    ActiveDrivingSessionResponse,
    BehaviorEventTimelineItemResponse,
    DriverResponseTimelineItemResponse,
    DrivingSessionEndRequest,
    DrivingSessionLocationsResponse,
    DrivingSessionStartRequest,
    DrivingSessionTimelineResponse,
    InterventionTimelineItemResponse,
    LocationSampleResponse,
)

PROFILE_ID = "274d9648-e78a-4630-a8e8-e63070dc3c19"


def start_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "profileId": PROFILE_ID,
        "startLocation": {"latitude": 37.5501, "longitude": 127.0734},
        "destination": {
            "providerPlaceId": " 111111 ",
            "name": " Test Destination ",
            "latitude": 37.5510,
            "longitude": 127.0737,
        },
    }
    payload.update(overrides)
    return payload


def test_start_request_normalizes_uuid_and_destination_values() -> None:
    request = DrivingSessionStartRequest(**start_payload())

    assert request.profile_id == PROFILE_ID
    assert request.destination is not None
    assert request.destination.provider_place_id == "111111"
    assert request.destination.name == "Test Destination"
    assert request.to_model_data() == {
        "profile_id": PROFILE_ID,
        "start_latitude": 37.5501,
        "start_longitude": 127.0734,
        "destination_name": "Test Destination",
        "destination_place_id": "111111",
    }


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        (start_payload(profileId="not-a-uuid"), "INVALID_PROFILE_ID"),
        (
            start_payload(startLocation={"latitude": True, "longitude": 127.0}),
            "INVALID_START_LOCATION",
        ),
        (
            start_payload(startLocation={"latitude": 91.0, "longitude": 127.0}),
            "INVALID_START_LOCATION",
        ),
        (
            start_payload(destination={"name": "", "latitude": 37.0, "longitude": 127.0}),
            "INVALID_DESTINATION",
        ),
        (
            start_payload(
                destination={
                    "providerPlaceId": "x" * 256,
                    "name": "Destination",
                    "latitude": 37.0,
                    "longitude": 127.0,
                }
            ),
            "INVALID_DESTINATION",
        ),
        (start_payload(accountId="not-allowed"), "extra_forbidden"),
    ],
)
def test_start_request_validation_errors(payload: dict[str, object], error_type: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        DrivingSessionStartRequest(**payload)

    assert exc_info.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ({"endReason": "MAYBE"}, "INVALID_END_REASON"),
        (
            {
                "endReason": "USER_REQUEST",
                "endLocation": {"latitude": False, "longitude": 127.0},
            },
            "INVALID_START_LOCATION",
        ),
        ({"endReason": "USER_REQUEST", "extra": "nope"}, "extra_forbidden"),
    ],
)
def test_end_request_validation_errors(payload: dict[str, object], error_type: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        DrivingSessionEndRequest(**payload)

    assert exc_info.value.errors()[0]["type"] == error_type


def test_active_response_serializes_camel_case_and_utc_datetime() -> None:
    response = ActiveDrivingSessionResponse(
        id="67371b45-204c-4d87-b8f7-8a334229a41e",
        profile_id=PROFILE_ID,
        status="ACTIVE",
        started_at=datetime(2026, 6, 30, 1, 2, 3, 123456),
        destination_name="Test Destination",
        model_version="vit-test",
        policy_version="policy-test",
        web_socket_url="/ws/v1/driving-sessions/67371b45-204c-4d87-b8f7-8a334229a41e",
    )

    payload = response.model_dump(by_alias=True, mode="json")

    assert payload["profileId"] == PROFILE_ID
    assert payload["startedAt"] == "2026-06-30T01:02:03.123456Z"
    assert payload["destinationName"] == "Test Destination"
    assert payload["webSocketUrl"].startswith("/ws/v1/driving-sessions/")


def test_timeline_response_serializes_contract_fields_only() -> None:
    response = DrivingSessionTimelineResponse(
        session_id="67371b45-204c-4d87-b8f7-8a334229a41e",
        events=[
            BehaviorEventTimelineItemResponse(
                event_id="b9ce8edb-1bd7-4aaf-9178-4894bf876603",
                behavior_type="PHONE_USE",
                status="ACTIVE",
                started_at=datetime(2026, 6, 30, 1, 2, 3, 123456),
                ended_at=None,
                duration_ms=None,
                average_confidence=0.87,
                maximum_confidence=0.94,
                risk_level=2,
                driving_state="MOVING",
                speed_kph=None,
                resolution_reason=None,
                interventions=[
                    InterventionTimelineItemResponse(
                        intervention_id="65045f20-4ae0-4471-af69-d18e74a67b02",
                        level=2,
                        intervention_type="WARNING",
                        ui_text="Watch the road.",
                        speech_text=None,
                        status="WAITING_RESPONSE",
                        responses=[
                            DriverResponseTimelineItemResponse(
                                response_type="BEHAVIOR_CORRECTED",
                                behavior_corrected=None,
                                response_latency_ms=None,
                                responded_at=datetime(2026, 6, 30, 1, 2, 6, 123456),
                            )
                        ],
                    )
                ],
            )
        ],
    )

    payload = response.model_dump(by_alias=True, mode="json")
    event = payload["events"][0]
    intervention = event["interventions"][0]
    driver_response = intervention["responses"][0]

    assert payload["sessionId"] == "67371b45-204c-4d87-b8f7-8a334229a41e"
    assert event["eventId"] == "b9ce8edb-1bd7-4aaf-9178-4894bf876603"
    assert event["startedAt"] == "2026-06-30T01:02:03.123456Z"
    assert event["endedAt"] is None
    assert event["durationMs"] is None
    assert event["speedKph"] is None
    assert event["resolutionReason"] is None
    assert event["averageConfidence"] == 0.87
    assert intervention["interventionId"] == "65045f20-4ae0-4471-af69-d18e74a67b02"
    assert intervention["speechText"] is None
    assert driver_response["respondedAt"] == "2026-06-30T01:02:06.123456Z"
    assert driver_response["behaviorCorrected"] is None
    assert driver_response["responseLatencyMs"] is None
    assert "profileId" not in payload
    assert "id" not in event
    assert "behaviorEventId" not in intervention
    assert "interventionId" not in driver_response


def test_locations_response_serializes_contract_fields_only() -> None:
    response = DrivingSessionLocationsResponse(
        session_id="67371b45-204c-4d87-b8f7-8a334229a41e",
        samples=[
            LocationSampleResponse(
                latitude=37.5501,
                longitude=127.0734,
                speed_kph=None,
                driving_state="TEMPORARY_STOP",
                accuracy_meters=None,
                source="GPS",
                recorded_at=datetime(2026, 6, 30, 1, 2, 3, 123456),
            )
        ],
        count=1,
    )

    payload = response.model_dump(by_alias=True, mode="json")
    sample = payload["samples"][0]

    assert payload["sessionId"] == "67371b45-204c-4d87-b8f7-8a334229a41e"
    assert payload["count"] == 1
    assert sample["speedKph"] is None
    assert sample["accuracyMeters"] is None
    assert sample["recordedAt"] == "2026-06-30T01:02:03.123456Z"
    assert "id" not in sample
    assert "sessionId" not in sample
