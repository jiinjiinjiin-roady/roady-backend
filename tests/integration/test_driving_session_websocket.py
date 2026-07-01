import os
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.api.dependencies import get_current_account
from app.api.v1.endpoints.driving_sessions import get_driver_monitoring_readiness
from app.core.time import format_utc_datetime, utc_now_for_api_response, utc_now_for_mysql_datetime
from app.db.session import AsyncSessionLocal
from app.models import Account, DriverProfile, DrivingSession

pytestmark = pytest.mark.skipif(
    not (os.getenv("MYSQL_HOST") and os.getenv("MYSQL_PASSWORD")),
    reason="MySQL integration tests require Docker Compose database environment.",
)


class FakeReadiness:
    def __init__(self, available: bool = True) -> None:
        self.available = available

    async def is_available(self) -> bool:
        return self.available


@dataclass(slots=True)
class WebSocketTestData:
    current_account: Account
    other_account: Account
    active_session_id: str
    completed_session_id: str
    aborted_session_id: str
    other_active_session_id: str


async def create_test_data() -> WebSocketTestData:
    now = utc_now_for_mysql_datetime()
    current_account = Account(
        id=str(uuid4()),
        email=f"ws-current-{uuid4().hex}@example.com",
    )
    other_account = Account(
        id=str(uuid4()),
        email=f"ws-other-{uuid4().hex}@example.com",
    )
    current_profile = DriverProfile(
        account_id=current_account.id,
        display_name="WebSocket Current",
        agent_call_name="WebSocket Current",
    )
    other_profile = DriverProfile(
        account_id=other_account.id,
        display_name="WebSocket Other",
        agent_call_name="WebSocket Other",
    )

    async with AsyncSessionLocal() as session:
        session.add_all([current_account, other_account])
        await session.flush()
        session.add_all([current_profile, other_profile])
        await session.flush()

        active_session = DrivingSession(
            profile_id=current_profile.id,
            model_version="vit-dms-1.0.0",
            policy_version="risk-policy-1.0.0",
        )
        completed_session = DrivingSession(
            profile_id=current_profile.id,
            status="COMPLETED",
            ended_at=now + timedelta(minutes=10),
            end_reason="USER_REQUEST",
            model_version="vit-dms-1.0.0",
            policy_version="risk-policy-1.0.0",
        )
        aborted_session = DrivingSession(
            profile_id=current_profile.id,
            status="ABORTED",
            ended_at=now + timedelta(minutes=11),
            end_reason="CAMERA_LOST",
            model_version="vit-dms-1.0.0",
            policy_version="risk-policy-1.0.0",
        )
        other_active_session = DrivingSession(
            profile_id=other_profile.id,
            model_version="vit-dms-1.0.0",
            policy_version="risk-policy-1.0.0",
        )
        session.add_all(
            [
                active_session,
                completed_session,
                aborted_session,
                other_active_session,
            ]
        )
        await session.commit()

    return WebSocketTestData(
        current_account=current_account,
        other_account=other_account,
        active_session_id=active_session.id,
        completed_session_id=completed_session.id,
        aborted_session_id=aborted_session.id,
        other_active_session_id=other_active_session.id,
    )


async def delete_test_accounts(*account_ids: str) -> None:
    async with AsyncSessionLocal() as session:
        if account_ids:
            await session.execute(delete(Account).where(Account.id.in_(account_ids)))
        await session.commit()


async def get_driving_session_status(session_id: str) -> str:
    async with AsyncSessionLocal() as session:
        driving_session = await session.get(DrivingSession, session_id)
        assert driving_session is not None
        return driving_session.status


def override_dependencies(app, account: Account, *, model_available: bool = True) -> None:
    async def current_account_override() -> Account:
        return account

    def readiness_override() -> FakeReadiness:
        return FakeReadiness(model_available)

    app.dependency_overrides[get_current_account] = current_account_override
    app.dependency_overrides[get_driver_monitoring_readiness] = readiness_override


def assert_denial(
    client: TestClient,
    path: str,
    *,
    status_code: int,
    error_code: str,
) -> None:
    with pytest.raises(WebSocketDenialResponse) as exc_info:
        with client.websocket_connect(path):
            raise AssertionError("WebSocket connection unexpectedly succeeded")

    response = exc_info.value
    assert response.status_code == status_code
    payload = response.json()
    assert payload["status"] == status_code
    assert payload["error"] == error_code
    assert "detail" not in payload


def wait_for_condition(predicate, timeout_seconds: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition was not met before timeout.")


def test_websocket_handshake_denial_responses(app) -> None:
    with TestClient(app) as client:
        data = client.portal.call(create_test_data)
        override_dependencies(app, data.current_account)

        try:
            assert_denial(
                client,
                "/ws/v1/driving-sessions/not-a-uuid",
                status_code=422,
                error_code="INVALID_SESSION_ID",
            )
            assert_denial(
                client,
                f"/ws/v1/driving-sessions/{uuid4()}",
                status_code=404,
                error_code="SESSION_NOT_FOUND",
            )
            assert_denial(
                client,
                f"/ws/v1/driving-sessions/{data.other_active_session_id}",
                status_code=404,
                error_code="SESSION_NOT_FOUND",
            )
            assert_denial(
                client,
                f"/ws/v1/driving-sessions/{data.completed_session_id}",
                status_code=409,
                error_code="SESSION_NOT_ACTIVE",
            )
            assert_denial(
                client,
                f"/ws/v1/driving-sessions/{data.aborted_session_id}",
                status_code=409,
                error_code="SESSION_NOT_ACTIVE",
            )

            app.dependency_overrides.clear()
            override_dependencies(app, data.current_account, model_available=False)
            assert_denial(
                client,
                f"/ws/v1/driving-sessions/{data.active_session_id}",
                status_code=503,
                error_code="MODEL_NOT_AVAILABLE",
            )
        finally:
            app.dependency_overrides.clear()
            client.portal.call(delete_test_accounts, data.current_account.id, data.other_account.id)


def test_websocket_success_session_ready_pong_and_cleanup(app) -> None:
    with TestClient(app) as client:
        data = client.portal.call(create_test_data)
        override_dependencies(app, data.current_account)

        try:
            with client.websocket_connect(
                f"/ws/v1/driving-sessions/{data.active_session_id}"
            ) as websocket:
                ready = websocket.receive_json()

                assert ready["type"] == "SESSION_READY"
                assert ready["payload"] == {
                    "sessionId": data.active_session_id,
                    "modelVersion": "vit-dms-1.0.0",
                    "policyVersion": "risk-policy-1.0.0",
                    "recommendedFrameFps": 5,
                    "locationIntervalMs": 1000,
                    "heartbeatIntervalMs": 10000,
                }
                assert app.state.websocket_connection_manager.active_count == 1
                assert app.state.session_runtime_registry.count == 1

                runtime = app.state.session_runtime_registry._runtimes[data.active_session_id]
                previous_heartbeat_at = runtime.last_heartbeat_at
                websocket.send_json(
                    {
                        "type": "PONG",
                        "occurredAt": format_utc_datetime(utc_now_for_api_response()),
                        "payload": {},
                    }
                )

                wait_for_condition(
                    lambda: runtime.last_heartbeat_at > previous_heartbeat_at,
                )

            wait_for_condition(lambda: app.state.websocket_connection_manager.active_count == 0)
            wait_for_condition(lambda: app.state.session_runtime_registry.count == 0)

            session_status = client.portal.call(get_driving_session_status, data.active_session_id)
            assert session_status == "ACTIVE"
        finally:
            app.dependency_overrides.clear()
            client.portal.call(delete_test_accounts, data.current_account.id, data.other_account.id)


@pytest.mark.parametrize(
    ("send_invalid_message", "expected_error"),
    [
        (lambda websocket: websocket.send_text("not-json"), "WEBSOCKET_PROTOCOL_ERROR"),
        (
            lambda websocket: websocket.send_json(
                {
                    "type": "LOCATION_UPDATE",
                    "occurredAt": format_utc_datetime(utc_now_for_api_response()),
                    "payload": {},
                }
            ),
            "WEBSOCKET_PROTOCOL_ERROR",
        ),
        (lambda websocket: websocket.send_bytes(b"\xff\xd8\xff"), "WEBSOCKET_PROTOCOL_ERROR"),
    ],
)
def test_websocket_protocol_errors_close_with_policy_violation(
    app,
    send_invalid_message,
    expected_error: str,
) -> None:
    with TestClient(app) as client:
        data = client.portal.call(create_test_data)
        override_dependencies(app, data.current_account)

        try:
            with client.websocket_connect(
                f"/ws/v1/driving-sessions/{data.active_session_id}"
            ) as websocket:
                assert websocket.receive_json()["type"] == "SESSION_READY"

                send_invalid_message(websocket)
                error_message = websocket.receive_json()

                assert error_message["type"] == "ERROR"
                assert error_message["payload"]["code"] == expected_error
                assert error_message["payload"]["recoverable"] is False

                with pytest.raises(WebSocketDisconnect) as exc_info:
                    websocket.receive_json()
                assert exc_info.value.code == 1008
        finally:
            app.dependency_overrides.clear()
            client.portal.call(delete_test_accounts, data.current_account.id, data.other_account.id)


def test_websocket_duplicate_connection_replaces_previous_connection(app) -> None:
    with TestClient(app) as client:
        data = client.portal.call(create_test_data)
        override_dependencies(app, data.current_account)

        try:
            with client.websocket_connect(
                f"/ws/v1/driving-sessions/{data.active_session_id}"
            ) as first:
                assert first.receive_json()["type"] == "SESSION_READY"

                with client.websocket_connect(
                    f"/ws/v1/driving-sessions/{data.active_session_id}"
                ) as second:
                    second_ready = second.receive_json()
                    assert second_ready["type"] == "SESSION_READY"
                    assert app.state.websocket_connection_manager.active_count == 1
                    assert app.state.session_runtime_registry.count == 1

                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        first.receive_json()
                    assert exc_info.value.code == 4001
                    assert app.state.websocket_connection_manager.active_count == 1
                    assert app.state.session_runtime_registry.count == 1

                wait_for_condition(lambda: app.state.websocket_connection_manager.active_count == 0)
                wait_for_condition(lambda: app.state.session_runtime_registry.count == 0)
        finally:
            app.dependency_overrides.clear()
            client.portal.call(delete_test_accounts, data.current_account.id, data.other_account.id)
