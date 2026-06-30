import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.session import get_session
from app.models import Account
from app.repositories.account_repository import AccountRepository

logger = logging.getLogger(__name__)


def get_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def get_settings_dependency() -> Settings:
    return get_settings()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings_dependency)]


async def get_current_account(
    session: DbSession,
    settings: AppSettings,
) -> Account:
    repository = AccountRepository(session)

    try:
        account = await repository.get_default_admin(settings.default_admin_account_id)
    except SQLAlchemyError as exc:
        logger.exception("Failed to load current account")
        raise AppException(
            "데이터베이스에 연결할 수 없습니다.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=ErrorCode.DATABASE_UNAVAILABLE,
        ) from exc

    if account is None:
        logger.error(
            "Default admin account does not exist account_id=%s",
            settings.default_admin_account_id,
        )
        raise AppException(
            "기본 관리자 계정을 찾을 수 없습니다.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
        )

    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]
