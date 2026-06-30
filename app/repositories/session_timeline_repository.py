from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BehaviorEvent, DriverResponse, Intervention


class SessionTimelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_behavior_events(self, session_id: str) -> list[BehaviorEvent]:
        result = await self.session.execute(
            select(BehaviorEvent)
            .where(BehaviorEvent.session_id == session_id)
            .order_by(BehaviorEvent.started_at, BehaviorEvent.id)
        )
        return list(result.scalars().all())

    async def list_interventions(self, event_ids: list[str]) -> list[Intervention]:
        if not event_ids:
            return []

        result = await self.session.execute(
            select(Intervention)
            .where(Intervention.behavior_event_id.in_(event_ids))
            .order_by(Intervention.started_at, Intervention.id)
        )
        return list(result.scalars().all())

    async def list_driver_responses(self, intervention_ids: list[str]) -> list[DriverResponse]:
        if not intervention_ids:
            return []

        result = await self.session.execute(
            select(DriverResponse)
            .where(DriverResponse.intervention_id.in_(intervention_ids))
            .order_by(DriverResponse.responded_at, DriverResponse.id)
        )
        return list(result.scalars().all())
