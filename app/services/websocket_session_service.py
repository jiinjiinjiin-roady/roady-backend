import logging

from fastapi import status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DrivingSessionStatus
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.integrations.driver_monitoring import DriverMonitoringReadiness
from app.models import Account, DrivingSession
from app.repositories.driving_session_repository import DrivingSessionRepository

logger = logging.getLogger(__name__)


class WebSocketSessionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        readiness: DriverMonitoringReadiness,
    ) -> None:
        self.session = session
        self.readiness = readiness
        self.driving_session_repository = DrivingSessionRepository(session)

    async def validate_connection(
        self,
        *,
        account: Account,
        session_id: str,
    ) -> DrivingSession:
        try:
            driving_session = await self.driving_session_repository.get_owned_by_account(
                account_id=account.id,
                session_id=session_id,
            )
            if driving_session is None:
                raise self._session_not_found()

            if driving_session.status != DrivingSessionStatus.ACTIVE.value:
                raise self._session_not_active()

            if not await self.readiness.is_available():
                raise self._model_not_available()

            return driving_session
        except AppException:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("WebSocket connection validation failed session_id=%s", session_id)
            raise AppException(
                "실시간 연결을 검증하지 못했습니다.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            ) from exc

    @staticmethod
    def _session_not_found() -> AppException:
        return AppException(
            "운전 세션을 찾을 수 없습니다.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=ErrorCode.SESSION_NOT_FOUND,
        )

    @staticmethod
    def _session_not_active() -> AppException:
        return AppException(
            "진행 중인 운전 세션만 실시간 연결할 수 있습니다.",
            status_code=status.HTTP_409_CONFLICT,
            error_code=ErrorCode.SESSION_NOT_ACTIVE,
        )

    @staticmethod
    def _model_not_available() -> AppException:
        return AppException(
            "운전자 행동 감지 모델을 사용할 수 없습니다.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=ErrorCode.MODEL_NOT_AVAILABLE,
        )
