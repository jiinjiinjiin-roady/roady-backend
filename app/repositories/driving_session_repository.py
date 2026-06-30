from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DrivingSessionStatus
from app.models import DrivingSession


class DrivingSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_active_session_for_profile(self, profile_id: str) -> bool:
        statement = select(
            exists().where(
                DrivingSession.profile_id == profile_id,
                DrivingSession.status == DrivingSessionStatus.ACTIVE.value,
            )
        )
        return bool(await self.session.scalar(statement))
