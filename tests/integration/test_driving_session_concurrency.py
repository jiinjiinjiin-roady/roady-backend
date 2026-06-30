import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.session import AsyncSessionLocal, dispose_engine
from app.models import Account, DriverProfile, DrivingSession
from app.schemas.driving_session import DrivingSessionStartRequest
from app.services.driving_session_service import DrivingSessionService

pytestmark = pytest.mark.skipif(
    not (os.getenv("MYSQL_HOST") and os.getenv("MYSQL_PASSWORD")),
    reason="MySQL integration tests require Docker Compose database environment.",
)


class AlwaysAvailableReadiness:
    async def is_available(self) -> bool:
        return True


def start_payload(profile_id: str) -> dict[str, object]:
    return {
        "profileId": profile_id,
        "startLocation": {"latitude": 37.5501, "longitude": 127.0734},
        "destination": {
            "providerPlaceId": "concurrent-destination",
            "name": "Concurrent Destination",
            "latitude": 37.5510,
            "longitude": 127.0737,
        },
    }


async def create_account_and_profile() -> tuple[Account, DriverProfile]:
    account = Account(id=str(uuid4()), email=f"session-concurrent-{uuid4().hex}@example.com")
    profile = DriverProfile(
        account_id=account.id,
        display_name="Concurrent Session",
        agent_call_name="Concurrent Session",
    )
    async with AsyncSessionLocal() as session:
        session.add(account)
        await session.flush()
        session.add(profile)
        await session.commit()
    return account, profile


async def delete_test_accounts(*account_ids: str) -> None:
    async with AsyncSessionLocal() as session:
        if account_ids:
            await session.execute(delete(Account).where(Account.id.in_(account_ids)))
        await session.commit()


async def test_concurrent_start_allows_one_active_session() -> None:
    account, profile = await create_account_and_profile()

    try:
        async def start_one() -> str:
            async with AsyncSessionLocal() as session:
                service = DrivingSessionService(
                    session=session,
                    settings=get_settings(),
                    readiness=AlwaysAvailableReadiness(),
                )
                try:
                    response = await service.start_session(
                        account,
                        DrivingSessionStartRequest(**start_payload(profile.id)),
                    )
                    return response.id
                except AppException as exc:
                    return exc.error_code

        results = await asyncio.gather(start_one(), start_one())

        async with AsyncSessionLocal() as session:
            active_count = await session.scalar(
                select(func.count())
                .select_from(DrivingSession)
                .where(
                    DrivingSession.profile_id == profile.id,
                    DrivingSession.status == "ACTIVE",
                )
            )

        assert results.count("ACTIVE_SESSION_EXISTS") == 1
        assert active_count == 1
    finally:
        await delete_test_accounts(account.id)
        await dispose_engine()
