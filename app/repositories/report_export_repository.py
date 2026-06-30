from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReportExport


class ReportExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_storage_keys_by_profile(self, profile_id: str) -> list[str]:
        result = await self.session.execute(
            select(ReportExport.storage_key).where(
                ReportExport.profile_id == profile_id,
                ReportExport.storage_key.is_not(None),
            )
        )
        return [storage_key for storage_key in result.scalars().all() if storage_key]
