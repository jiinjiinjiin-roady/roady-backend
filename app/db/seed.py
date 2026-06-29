import asyncio
import logging
from collections.abc import Callable
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal, dispose_engine
from app.models import Account

logger = logging.getLogger(__name__)

SeedResult = Literal["created", "updated", "unchanged"]


class SeedError(RuntimeError):
    pass


async def seed_default_admin_account(session: AsyncSession, settings: Settings) -> SeedResult:
    admin_id = settings.default_admin_account_id
    admin_email = settings.default_admin_email

    if admin_email is not None:
        result = await session.execute(
            select(Account).where(Account.email == admin_email, Account.id != admin_id)
        )
        conflicting_account = result.scalar_one_or_none()
        if conflicting_account is not None:
            raise SeedError(
                "Default admin email is already used by another account: "
                f"{conflicting_account.id}"
            )

    account = await session.get(Account, admin_id)

    if account is None:
        session.add(Account(id=admin_id, email=admin_email))
        return "created"

    if account.email != admin_email:
        account.email = admin_email
        return "updated"

    return "unchanged"


async def run_seed(
    settings: Settings | None = None,
    session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
) -> SeedResult:
    active_settings = settings or get_settings()

    async with session_factory() as session:
        try:
            result = await seed_default_admin_account(session, active_settings)
            await session.commit()
            logger.info("Default admin account seed completed: %s", result)
            return result
        except Exception:
            await session.rollback()
            logger.exception("Default admin account seed failed")
            raise


async def run_seed_command() -> SeedResult:
    try:
        return await run_seed()
    finally:
        await dispose_engine()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    try:
        asyncio.run(run_seed_command())
    except Exception as exc:
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
