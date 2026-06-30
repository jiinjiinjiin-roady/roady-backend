from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_default_admin(self, account_id: str) -> Account | None:
        return await self.session.get(Account, account_id)

    async def get_by_id_for_update(self, account_id: str) -> Account | None:
        result = await self.session.execute(
            select(Account).where(Account.id == account_id).with_for_update()
        )
        return result.scalar_one_or_none()
