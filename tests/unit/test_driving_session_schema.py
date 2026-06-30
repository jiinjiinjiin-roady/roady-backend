from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.driving_session import (
    ActiveDrivingSessionResponse,
    DrivingSessionEndRequest,
    DrivingSessionStartRequest,
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
