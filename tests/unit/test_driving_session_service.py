from datetime import datetime
from decimal import Decimal

import pytest

from app.core.exceptions import AppException
from app.services.driving_session_service import DrivingSessionService
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
