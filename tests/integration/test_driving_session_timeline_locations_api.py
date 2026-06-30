import os
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, event

from app.api.dependencies import get_current_account
from app.db.session import AsyncSessionLocal, dispose_engine, engine
from app.models import (
    Account,
    BehaviorEvent,
    DriverProfile,
    DriverResponse,
    DrivingSession,
    Intervention,
    LocationSample,
)

pytestmark = pytest.mark.skipif(
    not (os.getenv("MYSQL_HOST") and os.getenv("MYSQL_PASSWORD")),
    reason="MySQL integration tests require Docker Compose database environment.",
)

BASE_TIME = datetime(2026, 6, 28, 3, 10, 0)


def make_account(prefix: str) -> Account:
    return Account(id=str(uuid4()), email=f"{prefix}-{uuid4().hex}@example.com")


def make_profile(account_id: str, display_name: str) -> DriverProfile:
    normalized_name = display_name[:50]
    return DriverProfile(
        id=str(uuid4()),
        account_id=account_id,
        display_name=normalized_name,
        agent_call_name=normalized_name,
    )


def make_session(
    profile_id: str,
    *,
    status: str = "ACTIVE",
    started_at: datetime = BASE_TIME,
) -> DrivingSession:
    ended_at = None if status == "ACTIVE" else started_at + timedelta(minutes=10)
    end_reason = None if status == "ACTIVE" else "USER_REQUEST"
    return DrivingSession(
        profile_id=profile_id,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        end_reason=end_reason,
        model_version="vit-test",
        policy_version="policy-test",
    )


async def delete_test_accounts(*account_ids: str) -> None:
    async with AsyncSessionLocal() as session:
        if account_ids:
            await session.execute(delete(Account).where(Account.id.in_(account_ids)))
        await session.commit()


def override_current_account(app, account: Account) -> None:
    async def current_account_override() -> Account:
        return account

    app.dependency_overrides[get_current_account] = current_account_override


async def create_account_profile_session(
    *,
    prefix: str,
    status: str = "ACTIVE",
) -> tuple[Account, DriverProfile, DrivingSession]:
    account = make_account(prefix)
    profile = make_profile(account.id, f"{prefix} Profile")
    driving_session = make_session(profile.id, status=status)

    async with AsyncSessionLocal() as session:
        session.add(account)
        await session.flush()
        session.add(profile)
        await session.flush()
        session.add(driving_session)
        await session.commit()

    return account, profile, driving_session


async def seed_timeline_session(prefix: str = "timeline-api") -> tuple[Account, str]:
    account = make_account(prefix)
    profile = make_profile(account.id, f"{prefix} Profile")
    driving_session = make_session(profile.id)
    other_session = make_session(
        profile.id,
        status="COMPLETED",
        started_at=BASE_TIME - timedelta(days=1),
    )

    async with AsyncSessionLocal() as session:
        session.add(account)
        await session.flush()
        session.add(profile)
        await session.flush()
        session.add_all([driving_session, other_session])
        await session.flush()

        event_one = BehaviorEvent(
            id="00000000-0000-0000-0000-000000000001",
            session_id=driving_session.id,
            behavior_type="PHONE_USE",
            status="RESOLVED",
            started_at=BASE_TIME,
            ended_at=BASE_TIME + timedelta(seconds=6),
            duration_ms=6000,
            average_confidence=Decimal("0.8700"),
            maximum_confidence=Decimal("0.9400"),
            driving_state="MOVING",
            speed_kph=Decimal("38.50"),
            risk_level=2,
            resolution_reason="BEHAVIOR_CORRECTED",
        )
        event_two = BehaviorEvent(
            id="00000000-0000-0000-0000-000000000002",
            session_id=driving_session.id,
            behavior_type="DROWSINESS",
            started_at=BASE_TIME,
            average_confidence=Decimal("0.7500"),
            maximum_confidence=Decimal("0.8000"),
            driving_state="MOVING",
            risk_level=1,
        )
        event_three = BehaviorEvent(
            id="00000000-0000-0000-0000-000000000003",
            session_id=driving_session.id,
            behavior_type="GAZE_AWAY",
            status="RESOLVED",
            started_at=BASE_TIME + timedelta(seconds=30),
            ended_at=BASE_TIME + timedelta(seconds=35),
            duration_ms=5000,
            average_confidence=Decimal("0.8000"),
            maximum_confidence=Decimal("0.9000"),
            driving_state="TEMPORARY_STOP",
            speed_kph=None,
            risk_level=2,
            resolution_reason="USER_DISMISSED",
        )
        other_event = BehaviorEvent(
            session_id=other_session.id,
            behavior_type="PHONE_USE",
            started_at=BASE_TIME,
            average_confidence=Decimal("0.9000"),
            maximum_confidence=Decimal("0.9500"),
            driving_state="MOVING",
            risk_level=2,
        )
        session.add_all([event_two, event_three, event_one, other_event])
        await session.flush()

        intervention_one = Intervention(
            id="00000000-0000-0000-0000-000000000011",
            behavior_event_id=event_one.id,
            level=2,
            intervention_type="WARNING",
            ui_text="Phone use detected.",
            speech_text="Please put down your phone.",
            channels_json=["VOICE", "VISUAL"],
            status="RESOLVED",
            started_at=BASE_TIME + timedelta(seconds=1),
        )
        intervention_two = Intervention(
            id="00000000-0000-0000-0000-000000000012",
            behavior_event_id=event_one.id,
            level=3,
            intervention_type="WARNING",
            ui_text="Phone use still detected.",
            speech_text=None,
            channels_json=["VISUAL"],
            status="WAITING_RESPONSE",
            started_at=BASE_TIME + timedelta(seconds=1),
        )
        intervention_three = Intervention(
            id="00000000-0000-0000-0000-000000000013",
            behavior_event_id=event_three.id,
            level=1,
            intervention_type="RECOMMENDATION",
            ui_text="Eyes on the road.",
            speech_text=None,
            channels_json=["VISUAL"],
            status="DELIVERED",
            started_at=BASE_TIME + timedelta(seconds=31),
        )
        session.add_all([intervention_two, intervention_three, intervention_one])
        await session.flush()

        response_one = DriverResponse(
            id="00000000-0000-0000-0000-000000000021",
            intervention_id=intervention_one.id,
            response_type="BEHAVIOR_CORRECTED",
            behavior_corrected=True,
            response_latency_ms=2800,
            responded_at=BASE_TIME + timedelta(seconds=4),
        )
        response_two = DriverResponse(
            id="00000000-0000-0000-0000-000000000022",
            intervention_id=intervention_one.id,
            response_type="BUTTON_DISMISSED",
            behavior_corrected=None,
            response_latency_ms=None,
            responded_at=BASE_TIME + timedelta(seconds=4),
        )
        session.add_all([response_two, response_one])
        await session.commit()

    return account, driving_session.id


async def seed_location_session(prefix: str = "locations-api") -> tuple[Account, str]:
    account = make_account(prefix)
    profile = make_profile(account.id, f"{prefix} Profile")
    driving_session = make_session(profile.id)
    other_session = make_session(
        profile.id,
        status="COMPLETED",
        started_at=BASE_TIME - timedelta(days=2),
    )

    async with AsyncSessionLocal() as session:
        session.add(account)
        await session.flush()
        session.add(profile)
        await session.flush()
        session.add_all([driving_session, other_session])
        await session.flush()

        session.add_all(
            [
                LocationSample(
                    session_id=driving_session.id,
                    latitude=37.5501,
                    longitude=127.0734,
                    speed_kph=None,
                    driving_state="TEMPORARY_STOP",
                    accuracy_meters=None,
                    recorded_at=BASE_TIME,
                ),
                LocationSample(
                    session_id=driving_session.id,
                    latitude=37.5502,
                    longitude=127.0735,
                    speed_kph=Decimal("10.50"),
                    driving_state="MOVING",
                    accuracy_meters=Decimal("8.20"),
                    recorded_at=BASE_TIME + timedelta(seconds=10),
                ),
                LocationSample(
                    session_id=driving_session.id,
                    latitude=37.5503,
                    longitude=127.0736,
                    speed_kph=Decimal("20.00"),
                    driving_state="MOVING",
                    accuracy_meters=Decimal("7.00"),
                    recorded_at=BASE_TIME + timedelta(seconds=20),
                ),
                LocationSample(
                    session_id=driving_session.id,
                    latitude=37.5504,
                    longitude=127.0737,
                    speed_kph=Decimal("30.00"),
                    driving_state="MOVING",
                    accuracy_meters=Decimal("6.50"),
                    recorded_at=BASE_TIME + timedelta(seconds=30),
                ),
                LocationSample(
                    session_id=other_session.id,
                    latitude=38.0,
                    longitude=128.0,
                    driving_state="MOVING",
                    recorded_at=BASE_TIME,
                ),
            ]
        )
        await session.commit()

    return account, driving_session.id


async def test_timeline_api_returns_ordered_nested_events_and_empty_arrays(app, client) -> None:
    account, session_id = await seed_timeline_session()
    override_current_account(app, account)

    try:
        response = await client.get(f"/api/v1/driving-sessions/{session_id}/timeline")

        assert response.status_code == 200
        payload = response.json()
        assert payload["sessionId"] == session_id
        assert "profileId" not in payload
        assert [event["eventId"] for event in payload["events"]] == [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ]

        first_event = payload["events"][0]
        assert first_event["startedAt"] == "2026-06-28T03:10:00.000000Z"
        assert first_event["endedAt"] == "2026-06-28T03:10:06.000000Z"
        assert first_event["averageConfidence"] == 0.87
        assert first_event["maximumConfidence"] == 0.94
        assert first_event["speedKph"] == 38.5
        assert first_event["resolutionReason"] == "BEHAVIOR_CORRECTED"
        assert [item["interventionId"] for item in first_event["interventions"]] == [
            "00000000-0000-0000-0000-000000000011",
            "00000000-0000-0000-0000-000000000012",
        ]
        assert first_event["interventions"][1]["speechText"] is None
        assert first_event["interventions"][1]["responses"] == []
        assert [item["responseType"] for item in first_event["interventions"][0]["responses"]] == [
            "BEHAVIOR_CORRECTED",
            "BUTTON_DISMISSED",
        ]
        assert first_event["interventions"][0]["responses"][1]["behaviorCorrected"] is None
        assert first_event["interventions"][0]["responses"][1]["responseLatencyMs"] is None

        assert payload["events"][1]["status"] == "ACTIVE"
        assert payload["events"][1]["endedAt"] is None
        assert payload["events"][1]["durationMs"] is None
        assert payload["events"][1]["speedKph"] is None
        assert payload["events"][1]["resolutionReason"] is None
        assert payload["events"][1]["interventions"] == []
        assert payload["events"][2]["interventions"][0]["responses"] == []
    finally:
        app.dependency_overrides.clear()
        await delete_test_accounts(account.id)
        await dispose_engine()


async def test_timeline_api_uses_constant_bulk_query_count(app, client) -> None:
    account, session_id = await seed_timeline_session("timeline-query-count")
    override_current_account(app, account)
    statements: list[str] = []

    def before_cursor_execute(
        conn,
        cursor,
        statement: str,
        parameters,
        context,
        executemany,
    ) -> None:
        lowered = statement.lower()
        table_names = ("driving_sessions", "behavior_events", "interventions", "driver_responses")
        if lowered.lstrip().startswith("select") and any(name in lowered for name in table_names):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        response = await client.get(f"/api/v1/driving-sessions/{session_id}/timeline")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        app.dependency_overrides.clear()
        await delete_test_accounts(account.id)
        await dispose_engine()

    assert response.status_code == 200
    assert len(statements) == 4


async def test_timeline_and_locations_support_empty_active_completed_aborted_sessions(
    app,
    client,
) -> None:
    account = make_account("empty-session")
    profile = make_profile(account.id, "Empty Session")
    sessions = [
        make_session(profile.id, status="ACTIVE", started_at=BASE_TIME),
        make_session(profile.id, status="COMPLETED", started_at=BASE_TIME + timedelta(hours=1)),
        make_session(profile.id, status="ABORTED", started_at=BASE_TIME + timedelta(hours=2)),
    ]

    async with AsyncSessionLocal() as db_session:
        db_session.add(account)
        await db_session.flush()
        db_session.add(profile)
        await db_session.flush()
        db_session.add_all(sessions)
        await db_session.commit()

    override_current_account(app, account)

    try:
        for driving_session in sessions:
            timeline = await client.get(
                f"/api/v1/driving-sessions/{driving_session.id}/timeline"
            )
            locations = await client.get(
                f"/api/v1/driving-sessions/{driving_session.id}/locations"
            )

            assert timeline.status_code == 200
            assert timeline.json() == {"sessionId": driving_session.id, "events": []}
            assert locations.status_code == 200
            assert locations.json() == {
                "sessionId": driving_session.id,
                "samples": [],
                "count": 0,
            }
    finally:
        app.dependency_overrides.clear()
        await delete_test_accounts(account.id)
        await dispose_engine()


async def test_locations_api_filters_orders_limits_and_counts_returned_samples(
    app,
    client,
) -> None:
    account, session_id = await seed_location_session()
    override_current_account(app, account)

    try:
        response = await client.get(f"/api/v1/driving-sessions/{session_id}/locations")
        assert response.status_code == 200
        payload = response.json()
        assert payload["sessionId"] == session_id
        assert payload["count"] == 4
        assert [sample["recordedAt"] for sample in payload["samples"]] == [
            "2026-06-28T03:10:00.000000Z",
            "2026-06-28T03:10:10.000000Z",
            "2026-06-28T03:10:20.000000Z",
            "2026-06-28T03:10:30.000000Z",
        ]
        assert payload["samples"][0]["speedKph"] is None
        assert payload["samples"][0]["accuracyMeters"] is None
        assert payload["samples"][1]["speedKph"] == 10.5
        assert payload["samples"][1]["accuracyMeters"] == 8.2
        assert "id" not in payload["samples"][0]
        assert "sessionId" not in payload["samples"][0]

        from_only = await client.get(
            f"/api/v1/driving-sessions/{session_id}/locations",
            params={"from": "2026-06-28T03:10:10Z"},
        )
        assert from_only.status_code == 200
        assert from_only.json()["count"] == 3

        to_only = await client.get(
            f"/api/v1/driving-sessions/{session_id}/locations",
            params={"to": "2026-06-28T03:10:20Z"},
        )
        assert to_only.status_code == 200
        assert to_only.json()["count"] == 3

        offset_range = await client.get(
            f"/api/v1/driving-sessions/{session_id}/locations",
            params={
                "from": "2026-06-28T12:10:10+09:00",
                "to": "2026-06-28T12:10:20+09:00",
            },
        )
        assert offset_range.status_code == 200
        assert offset_range.json()["count"] == 2

        limited = await client.get(
            f"/api/v1/driving-sessions/{session_id}/locations",
            params={"limit": 2},
        )
        assert limited.status_code == 200
        assert limited.json()["count"] == 2
        assert limited.json()["samples"][-1]["recordedAt"] == "2026-06-28T03:10:10.000000Z"

        empty = await client.get(
            f"/api/v1/driving-sessions/{session_id}/locations",
            params={"from": "2026-06-28T03:11:00Z"},
        )
        assert empty.status_code == 200
        assert empty.json() == {"sessionId": session_id, "samples": [], "count": 0}
    finally:
        app.dependency_overrides.clear()
        await delete_test_accounts(account.id)
        await dispose_engine()


@pytest.mark.parametrize(
    ("params", "error_code"),
    [
        ({"from": "2026-06-28T03:10:30Z", "to": "2026-06-28T03:10:00Z"}, "INVALID_TIME_RANGE"),
        ({"from": "2026-06-28T03:10:00"}, "INVALID_TIME_RANGE"),
        ({"from": "not-a-date"}, "INVALID_TIME_RANGE"),
        ({"limit": 0}, "LOCATION_LIMIT_EXCEEDED"),
        ({"limit": 5001}, "LOCATION_LIMIT_EXCEEDED"),
        ({"limit": "many"}, "LOCATION_LIMIT_EXCEEDED"),
    ],
)
async def test_locations_api_validation_errors(
    app,
    client,
    params: dict[str, object],
    error_code: str,
) -> None:
    account, session_id = await seed_location_session(f"location-error-{uuid4().hex}")
    override_current_account(app, account)

    try:
        response = await client.get(
            f"/api/v1/driving-sessions/{session_id}/locations",
            params=params,
        )

        assert response.status_code == 422
        assert response.json()["error"] == error_code
        assert "detail" not in response.json()
    finally:
        app.dependency_overrides.clear()
        await delete_test_accounts(account.id)
        await dispose_engine()


async def test_timeline_and_locations_reject_other_account_and_invalid_session_id(
    app,
    client,
) -> None:
    current_account, _, _ = await create_account_profile_session(prefix="current-account")
    other_account, _, other_session = await create_account_profile_session(prefix="other-account")
    override_current_account(app, current_account)

    try:
        other_timeline = await client.get(
            f"/api/v1/driving-sessions/{other_session.id}/timeline"
        )
        other_locations = await client.get(
            f"/api/v1/driving-sessions/{other_session.id}/locations"
        )
        invalid_timeline = await client.get("/api/v1/driving-sessions/not-a-uuid/timeline")
        invalid_locations = await client.get("/api/v1/driving-sessions/not-a-uuid/locations")
        missing_timeline = await client.get(f"/api/v1/driving-sessions/{uuid4()}/timeline")
        missing_locations = await client.get(f"/api/v1/driving-sessions/{uuid4()}/locations")

        assert other_timeline.status_code == 404
        assert other_timeline.json()["error"] == "SESSION_NOT_FOUND"
        assert other_locations.status_code == 404
        assert other_locations.json()["error"] == "SESSION_NOT_FOUND"
        assert invalid_timeline.status_code == 422
        assert invalid_timeline.json()["error"] == "INVALID_SESSION_ID"
        assert invalid_locations.status_code == 422
        assert invalid_locations.json()["error"] == "INVALID_SESSION_ID"
        assert missing_timeline.status_code == 404
        assert missing_timeline.json()["error"] == "SESSION_NOT_FOUND"
        assert missing_locations.status_code == 404
        assert missing_locations.json()["error"] == "SESSION_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
        await delete_test_accounts(current_account.id, other_account.id)
        await dispose_engine()
