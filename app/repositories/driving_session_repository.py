from datetime import datetime

from sqlalchemy import desc, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    BehaviorEventStatus,
    BehaviorResolutionReason,
    ConversationStatus,
    DrivingSessionStatus,
    InterventionStatus,
)
from app.models import AgentConversation, BehaviorEvent, DriverProfile, DrivingSession, Intervention


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

    async def get_active_by_profile(self, profile_id: str) -> DrivingSession | None:
        result = await self.session.execute(
            select(DrivingSession).where(
                DrivingSession.profile_id == profile_id,
                DrivingSession.status == DrivingSessionStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none()

    async def get_owned_by_account(
        self,
        *,
        account_id: str,
        session_id: str,
    ) -> DrivingSession | None:
        result = await self.session.execute(
            select(DrivingSession)
            .join(DriverProfile, DrivingSession.profile_id == DriverProfile.id)
            .where(
                DrivingSession.id == session_id,
                DriverProfile.account_id == account_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_owned_by_account_for_update(
        self,
        *,
        account_id: str,
        session_id: str,
    ) -> DrivingSession | None:
        result = await self.session.execute(
            select(DrivingSession)
            .join(DriverProfile, DrivingSession.profile_id == DriverProfile.id)
            .where(
                DrivingSession.id == session_id,
                DriverProfile.account_id == account_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_by_profile(
        self,
        *,
        profile_id: str,
        status_filter: str | None = None,
        started_from: datetime | None = None,
        started_to_exclusive: datetime | None = None,
    ) -> int:
        conditions = self._history_conditions(
            profile_id=profile_id,
            status_filter=status_filter,
            started_from=started_from,
            started_to_exclusive=started_to_exclusive,
        )
        count = await self.session.scalar(
            select(func.count()).select_from(DrivingSession).where(*conditions)
        )
        return int(count or 0)

    async def list_by_profile(
        self,
        *,
        profile_id: str,
        page: int,
        size: int,
        status_filter: str | None = None,
        started_from: datetime | None = None,
        started_to_exclusive: datetime | None = None,
    ) -> list[tuple[DrivingSession, int]]:
        offset = (page - 1) * size
        behavior_counts = (
            select(
                BehaviorEvent.session_id.label("session_id"),
                func.count(BehaviorEvent.id).label("behavior_event_count"),
            )
            .group_by(BehaviorEvent.session_id)
            .subquery()
        )
        conditions = self._history_conditions(
            profile_id=profile_id,
            status_filter=status_filter,
            started_from=started_from,
            started_to_exclusive=started_to_exclusive,
        )
        result = await self.session.execute(
            select(
                DrivingSession,
                func.coalesce(behavior_counts.c.behavior_event_count, 0),
            )
            .outerjoin(
                behavior_counts,
                behavior_counts.c.session_id == DrivingSession.id,
            )
            .where(*conditions)
            .order_by(desc(DrivingSession.started_at), desc(DrivingSession.id))
            .offset(offset)
            .limit(size)
        )
        return [(row[0], int(row[1] or 0)) for row in result.all()]

    async def close_active_behavior_events(self, *, session_id: str, ended_at: datetime) -> None:
        result = await self.session.execute(
            select(BehaviorEvent).where(
                BehaviorEvent.session_id == session_id,
                BehaviorEvent.status == BehaviorEventStatus.ACTIVE.value,
            )
        )
        active_events = list(result.scalars().all())
        for event in active_events:
            event.status = BehaviorEventStatus.RESOLVED.value
            event.ended_at = ended_at
            event.duration_ms = max(0, int((ended_at - event.started_at).total_seconds() * 1000))
            event.resolution_reason = BehaviorResolutionReason.SESSION_ENDED.value

    async def cancel_open_interventions(self, *, session_id: str, ended_at: datetime) -> None:
        event_ids = select(BehaviorEvent.id).where(BehaviorEvent.session_id == session_id)
        await self.session.execute(
            update(Intervention)
            .where(
                Intervention.behavior_event_id.in_(event_ids),
                Intervention.status.in_(
                    [
                        InterventionStatus.CREATED.value,
                        InterventionStatus.DELIVERED.value,
                        InterventionStatus.WAITING_RESPONSE.value,
                    ]
                ),
            )
            .values(status=InterventionStatus.CANCELLED.value, ended_at=ended_at)
        )

    async def abort_active_conversations(self, *, session_id: str, ended_at: datetime) -> None:
        await self.session.execute(
            update(AgentConversation)
            .where(
                AgentConversation.session_id == session_id,
                AgentConversation.status == ConversationStatus.ACTIVE.value,
            )
            .values(status=ConversationStatus.ABORTED.value, ended_at=ended_at)
        )

    def add(self, driving_session: DrivingSession) -> None:
        self.session.add(driving_session)

    @staticmethod
    def _history_conditions(
        *,
        profile_id: str,
        status_filter: str | None,
        started_from: datetime | None,
        started_to_exclusive: datetime | None,
    ) -> list[object]:
        conditions: list[object] = [DrivingSession.profile_id == profile_id]
        if status_filter is not None:
            conditions.append(DrivingSession.status == status_filter)
        if started_from is not None:
            conditions.append(DrivingSession.started_at >= started_from)
        if started_to_exclusive is not None:
            conditions.append(DrivingSession.started_at < started_to_exclusive)
        return conditions
