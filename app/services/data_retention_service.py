from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConversationStatus, ReportExportStatus
from app.core.time import utc_now_for_mysql_datetime
from app.models import AgentConversation, DrivingSession, LocationSample, ReportExport
from app.realtime.session_runtime import SessionRuntimeRegistry


@dataclass(frozen=True, slots=True)
class DataRetentionCleanupResult:
    session_runtime_removed: bool
    location_samples_deleted: int
    report_exports_deleted: int
    agent_conversations_deleted: int


class DataRetentionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        runtime_registry: SessionRuntimeRegistry | None = None,
    ) -> None:
        self.session = session
        self.runtime_registry = runtime_registry

    async def cleanup_session_data(
        self,
        *,
        session_id: str,
        location_sample_retention_days: int = 7,
        agent_log_retention_days: int = 30,
        now: datetime | None = None,
    ) -> DataRetentionCleanupResult:
        reference_time = now or utc_now_for_mysql_datetime()
        runtime_removed = False
        if self.runtime_registry is not None:
            runtime_removed = await self.runtime_registry.remove(session_id)

        location_deleted = await self.delete_expired_location_samples(
            session_id=session_id,
            cutoff=reference_time - timedelta(days=location_sample_retention_days),
        )
        report_deleted = await self.delete_expired_report_exports(now=reference_time)
        conversation_deleted = await self.delete_expired_agent_conversations(
            session_id=session_id,
            cutoff=reference_time - timedelta(days=agent_log_retention_days),
        )
        await self.session.commit()
        return DataRetentionCleanupResult(
            session_runtime_removed=runtime_removed,
            location_samples_deleted=location_deleted,
            report_exports_deleted=report_deleted,
            agent_conversations_deleted=conversation_deleted,
        )

    async def delete_expired_location_samples(self, *, session_id: str, cutoff: datetime) -> int:
        statement = delete(LocationSample).where(
            LocationSample.session_id == session_id,
            LocationSample.recorded_at < cutoff,
            LocationSample.session_id.in_(
                self._ended_session_ids(session_id=session_id, ended_before=cutoff)
            ),
        )
        result = await self.session.execute(statement)
        return int(result.rowcount or 0)

    async def delete_expired_report_exports(self, *, now: datetime) -> int:
        result = await self.session.execute(
            delete(ReportExport).where(
                ReportExport.expires_at.is_not(None),
                ReportExport.expires_at < now,
                ReportExport.export_status.in_(
                    [
                        ReportExportStatus.COMPLETED.value,
                        ReportExportStatus.FAILED.value,
                    ]
                ),
            )
        )
        return int(result.rowcount or 0)

    async def delete_expired_agent_conversations(self, *, session_id: str, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(AgentConversation).where(
                AgentConversation.session_id == session_id,
                AgentConversation.status != ConversationStatus.ACTIVE.value,
                AgentConversation.ended_at.is_not(None),
                AgentConversation.ended_at < cutoff,
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def _ended_session_ids(*, session_id: str, ended_before: datetime):
        from sqlalchemy import select

        return select(DrivingSession.id).where(
            DrivingSession.id == session_id,
            DrivingSession.ended_at.is_not(None),
            DrivingSession.ended_at < ended_before,
        )
