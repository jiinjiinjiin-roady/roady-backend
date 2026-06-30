from dataclasses import dataclass

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BehaviorEvent, DriverResponse, Intervention


@dataclass(frozen=True)
class SessionSummary:
    behavior_event_count: int
    intervention_count: int
    corrected_behavior_count: int
    average_response_latency_ms: float | None


class SessionSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(self, session_id: str) -> SessionSummary:
        behavior_count = await self.session.scalar(
            select(func.count())
            .select_from(BehaviorEvent)
            .where(BehaviorEvent.session_id == session_id)
        )
        intervention_count = await self.session.scalar(
            select(func.count())
            .select_from(Intervention)
            .join(BehaviorEvent, Intervention.behavior_event_id == BehaviorEvent.id)
            .where(BehaviorEvent.session_id == session_id)
        )
        corrected_count = await self.session.scalar(
            select(func.count(distinct(Intervention.id)))
            .select_from(Intervention)
            .join(BehaviorEvent, Intervention.behavior_event_id == BehaviorEvent.id)
            .join(DriverResponse, DriverResponse.intervention_id == Intervention.id)
            .where(
                BehaviorEvent.session_id == session_id,
                DriverResponse.behavior_corrected.is_(True),
            )
        )
        average_latency = await self.session.scalar(
            select(func.avg(DriverResponse.response_latency_ms))
            .select_from(DriverResponse)
            .join(Intervention, DriverResponse.intervention_id == Intervention.id)
            .join(BehaviorEvent, Intervention.behavior_event_id == BehaviorEvent.id)
            .where(
                BehaviorEvent.session_id == session_id,
                DriverResponse.response_latency_ms.is_not(None),
            )
        )

        return SessionSummary(
            behavior_event_count=int(behavior_count or 0),
            intervention_count=int(intervention_count or 0),
            corrected_behavior_count=int(corrected_count or 0),
            average_response_latency_ms=(
                None if average_latency is None else round(float(average_latency), 1)
            ),
        )
