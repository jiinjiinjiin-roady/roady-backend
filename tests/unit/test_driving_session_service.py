from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppException
from app.services.driving_session_service import (
    DEFAULT_LOCATION_SAMPLE_LIMIT,
    DrivingSessionService,
)
from app.utils.distance import Coordinate


def test_end_status_mapping() -> None:
    assert DrivingSessionService._end_status_for_reason("USER_REQUEST") == "COMPLETED"
    assert DrivingSessionService._end_status_for_reason("CAMERA_LOST") == "ABORTED"
    assert DrivingSessionService._end_status_for_reason("UNKNOWN") == "ABORTED"


@pytest.mark.parametrize(
    ("page", "size", "error_code"),
    [
        (0, 20, "INVALID_PAGE"),
        (1, 0, "INVALID_PAGE_SIZE"),
        (1, 101, "INVALID_PAGE_SIZE"),
    ],
)
def test_history_pagination_validation(page: int, size: int, error_code: str) -> None:
    with pytest.raises(AppException) as exc_info:
        DrivingSessionService._validate_pagination(page, size)

    assert exc_info.value.error_code == error_code


def test_history_status_validation() -> None:
    assert DrivingSessionService._validate_status_filter(None) is None
    assert DrivingSessionService._validate_status_filter("ACTIVE") == "ACTIVE"

    with pytest.raises(AppException) as exc_info:
        DrivingSessionService._validate_status_filter("PAUSED")

    assert exc_info.value.error_code == "INVALID_SESSION_STATUS"


@pytest.mark.parametrize(
    ("started_from", "started_to"),
    [
        ("2026-06-30", "2026-06-29"),
        ("2026-6-30", None),
        (None, "bad-date"),
    ],
)
def test_history_date_range_validation(started_from: str | None, started_to: str | None) -> None:
    with pytest.raises(AppException) as exc_info:
        DrivingSessionService._parse_date_range(
            started_from=started_from,
            started_to=started_to,
        )

    assert exc_info.value.error_code == "INVALID_DATE_RANGE"


def test_history_date_range_uses_inclusive_to_date() -> None:
    started_from, started_to = DrivingSessionService._parse_date_range(
        started_from="2026-06-29",
        started_to="2026-06-30",
    )

    assert started_from == datetime(2026, 6, 29, 0, 0, 0)
    assert started_to == datetime(2026, 7, 1, 0, 0, 0)


@pytest.mark.parametrize(
    ("from_value", "to_value", "expected_from", "expected_to"),
    [
        (None, None, None, None),
        ("2026-06-28T03:10:00Z", None, datetime(2026, 6, 28, 3, 10, 0), None),
        (None, "2026-06-28T03:10:00Z", None, datetime(2026, 6, 28, 3, 10, 0)),
        (
            "2026-06-28T12:10:00+09:00",
            "2026-06-28T12:20:00+09:00",
            datetime(2026, 6, 28, 3, 10, 0),
            datetime(2026, 6, 28, 3, 20, 0),
        ),
        (
            "2026-06-28T03:10:00Z",
            "2026-06-28T03:10:00Z",
            datetime(2026, 6, 28, 3, 10, 0),
            datetime(2026, 6, 28, 3, 10, 0),
        ),
    ],
)
def test_location_query_time_validation_and_utc_normalization(
    from_value: str | None,
    to_value: str | None,
    expected_from: datetime | None,
    expected_to: datetime | None,
) -> None:
    recorded_from, recorded_to, limit = DrivingSessionService._parse_location_query(
        from_value=from_value,
        to_value=to_value,
        limit=DEFAULT_LOCATION_SAMPLE_LIMIT,
    )

    assert recorded_from == expected_from
    assert recorded_to == expected_to
    assert limit == DEFAULT_LOCATION_SAMPLE_LIMIT


@pytest.mark.parametrize(
    ("from_value", "to_value"),
    [
        ("2026-06-28T03:20:00Z", "2026-06-28T03:10:00Z"),
        ("2026-06-28T03:10:00", None),
        ("not-a-date", None),
        (None, ""),
    ],
)
def test_location_query_time_validation_errors(
    from_value: str | None,
    to_value: str | None,
) -> None:
    with pytest.raises(AppException) as exc_info:
        DrivingSessionService._parse_location_query(
            from_value=from_value,
            to_value=to_value,
            limit=DEFAULT_LOCATION_SAMPLE_LIMIT,
        )

    assert exc_info.value.error_code == "INVALID_TIME_RANGE"


@pytest.mark.parametrize("limit", [1, DEFAULT_LOCATION_SAMPLE_LIMIT, 5000])
def test_location_limit_accepts_valid_values(limit: int) -> None:
    assert DrivingSessionService._validate_location_limit(limit) == limit


@pytest.mark.parametrize("limit", [0, 5001])
def test_location_limit_rejects_invalid_values(limit: int) -> None:
    with pytest.raises(AppException) as exc_info:
        DrivingSessionService._validate_location_limit(limit)

    assert exc_info.value.error_code == "LOCATION_LIMIT_EXCEEDED"


def test_timeline_response_groups_interventions_and_responses() -> None:
    event_without_interventions = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        behavior_type="DROWSINESS",
        status="ACTIVE",
        started_at=datetime(2026, 6, 30, 1, 0, 0),
        ended_at=None,
        duration_ms=None,
        average_confidence=Decimal("0.7500"),
        maximum_confidence=Decimal("0.8000"),
        risk_level=1,
        driving_state="MOVING",
        speed_kph=None,
        resolution_reason=None,
    )
    event_with_interventions = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        behavior_type="PHONE_USE",
        status="RESOLVED",
        started_at=datetime(2026, 6, 30, 1, 1, 0),
        ended_at=datetime(2026, 6, 30, 1, 1, 6),
        duration_ms=6000,
        average_confidence=Decimal("0.8700"),
        maximum_confidence=Decimal("0.9400"),
        risk_level=2,
        driving_state="MOVING",
        speed_kph=Decimal("38.50"),
        resolution_reason="BEHAVIOR_CORRECTED",
    )
    intervention_with_response = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000011",
        behavior_event_id=event_with_interventions.id,
        level=2,
        intervention_type="WARNING",
        ui_text="Watch the road.",
        speech_text="Please watch the road.",
        status="RESOLVED",
    )
    intervention_without_response = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000012",
        behavior_event_id=event_with_interventions.id,
        level=3,
        intervention_type="WARNING",
        ui_text="Still detected.",
        speech_text=None,
        status="WAITING_RESPONSE",
    )
    response = SimpleNamespace(
        intervention_id=intervention_with_response.id,
        response_type="BEHAVIOR_CORRECTED",
        behavior_corrected=True,
        response_latency_ms=2800,
        responded_at=datetime(2026, 6, 30, 1, 1, 4, 800000),
    )

    timeline = DrivingSessionService._build_timeline_response(
        session_id="67371b45-204c-4d87-b8f7-8a334229a41e",
        events=[event_without_interventions, event_with_interventions],
        interventions=[intervention_with_response, intervention_without_response],
        responses=[response],
    )
    payload = timeline.model_dump(by_alias=True, mode="json")

    assert [event["eventId"] for event in payload["events"]] == [
        event_without_interventions.id,
        event_with_interventions.id,
    ]
    assert payload["events"][0]["interventions"] == []
    assert [item["interventionId"] for item in payload["events"][1]["interventions"]] == [
        intervention_with_response.id,
        intervention_without_response.id,
    ]
    assert payload["events"][1]["interventions"][0]["responses"][0]["responseType"] == (
        "BEHAVIOR_CORRECTED"
    )
    assert payload["events"][1]["interventions"][1]["responses"] == []


@pytest.mark.parametrize(
    ("distance_meters", "duration_seconds", "expected"),
    [
        (0, 0, Decimal("0.00")),
        (1000, 0, Decimal("0.00")),
        (1000, 180, Decimal("20.0")),
    ],
)
def test_average_speed_calculation(
    distance_meters: int,
    duration_seconds: int,
    expected: Decimal,
) -> None:
    assert (
        DrivingSessionService._calculate_average_speed(distance_meters, duration_seconds)
        == expected
    )


def test_distance_calculation_uses_start_samples_and_end() -> None:
    class Session:
        start_latitude = 0.0
        start_longitude = 0.0

    distance = DrivingSessionService._calculate_distance(
        Session(),  # type: ignore[arg-type]
        [Coordinate(0.0, 1.0)],
        Coordinate(0.0, 2.0),
    )

    assert distance == 222390
