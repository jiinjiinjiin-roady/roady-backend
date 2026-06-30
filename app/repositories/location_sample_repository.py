from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LocationSample
from app.utils.distance import Coordinate


class LocationSampleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_coordinates_by_session(self, session_id: str) -> list[Coordinate]:
        result = await self.session.execute(
            select(LocationSample.latitude, LocationSample.longitude)
            .where(LocationSample.session_id == session_id)
            .order_by(LocationSample.recorded_at, LocationSample.id)
        )
        return [
            Coordinate(latitude=float(latitude), longitude=float(longitude))
            for latitude, longitude in result.all()
        ]

    async def list_by_session(
        self,
        *,
        session_id: str,
        recorded_from: datetime | None = None,
        recorded_to: datetime | None = None,
        limit: int,
    ) -> list[LocationSample]:
        conditions: list[object] = [LocationSample.session_id == session_id]
        if recorded_from is not None:
            conditions.append(LocationSample.recorded_at >= recorded_from)
        if recorded_to is not None:
            conditions.append(LocationSample.recorded_at <= recorded_to)

        result = await self.session.execute(
            select(LocationSample)
            .where(*conditions)
            .order_by(LocationSample.recorded_at, LocationSample.id)
            .limit(limit)
        )
        return list(result.scalars().all())
