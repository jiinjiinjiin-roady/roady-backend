from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import DrivingSessionStatus, SessionEndReason
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.time import utc_now_for_mysql_datetime
from app.integrations.driver_monitoring import DriverMonitoringReadiness
from app.models import Account, DrivingSession
from app.repositories.driving_session_repository import DrivingSessionRepository
from app.repositories.location_sample_repository import LocationSampleRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.session_summary_repository import SessionSummary, SessionSummaryRepository
from app.schemas.driving_session import (
    ActiveDrivingSessionResponse,
    CoordinateResponse,
    DrivingSessionDetailResponse,
    DrivingSessionEndRequest,
    DrivingSessionEndResponse,
    DrivingSessionHistoryItemResponse,
    DrivingSessionHistoryResponse,
    DrivingSessionStartRequest,
    DrivingSessionStartResponse,
    DrivingSessionSummaryResponse,
    SessionStartDestinationResponse,
)
from app.utils.distance import Coordinate, total_distance_meters

logger = logging.getLogger(__name__)

DEFAULT_DRIVING_SESSION_PAGE = 1
DEFAULT_DRIVING_SESSION_SIZE = 20
MAX_DRIVING_SESSION_SIZE = 100


class DrivingSessionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        readiness: DriverMonitoringReadiness,
    ) -> None:
        self.session = session
        self.settings = settings
        self.readiness = readiness
        self.profile_repository = ProfileRepository(session)
        self.driving_session_repository = DrivingSessionRepository(session)
        self.location_sample_repository = LocationSampleRepository(session)
        self.summary_repository = SessionSummaryRepository(session)

    async def start_session(
        self,
        account: Account,
        request: DrivingSessionStartRequest,
    ) -> DrivingSessionStartResponse:
        try:
            profile = await self.profile_repository.get_by_account_for_update(
                account.id,
                request.profile_id,
            )
            if profile is None:
                raise self._profile_not_found()

            active_session = await self.driving_session_repository.get_active_by_profile(
                profile.id,
            )
            if active_session is not None:
                raise self._active_session_exists()

            if not await self.readiness.is_available():
                raise self._model_not_available()

            started_at = utc_now_for_mysql_datetime()
            driving_session = DrivingSession(
                **request.to_model_data(),
                status=DrivingSessionStatus.ACTIVE.value,
                started_at=started_at,
                distance_meters=0,
                duration_seconds=0,
                average_speed_kph=None,
                safety_score=None,
                model_version=self.settings.model_version,
                policy_version=self.settings.policy_version,
            )
            self.driving_session_repository.add(driving_session)
            await self.session.flush()
            await self.session.refresh(driving_session)
            await self.session.commit()
            return self._to_start_response(driving_session)
        except AppException:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            logger.exception(
                "Driving session start integrity error profile_id=%s",
                request.profile_id,
            )
            raise self._active_session_exists() from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception(
                "Driving session start database error profile_id=%s",
                request.profile_id,
            )
            raise self._internal_error("Failed to start driving session.") from exc

    async def get_active_session(
        self,
        account: Account,
        profile_id: str,
    ) -> ActiveDrivingSessionResponse | None:
        try:
            profile = await self.profile_repository.get_by_account(account.id, profile_id)
            if profile is None:
                raise self._profile_not_found()

            active_session = await self.driving_session_repository.get_active_by_profile(profile.id)
        except AppException:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Active driving session query failed profile_id=%s", profile_id)
            raise self._internal_error("Failed to load active driving session.") from exc

        if active_session is None:
            return None

        return self._to_active_response(active_session)

    async def get_session_detail(
        self,
        account: Account,
        session_id: str,
    ) -> DrivingSessionDetailResponse:
        try:
            driving_session = await self.driving_session_repository.get_owned_by_account(
                account_id=account.id,
                session_id=session_id,
            )
            if driving_session is None:
                raise self._session_not_found()

            summary = await self.summary_repository.get_summary(driving_session.id)
        except AppException:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Driving session detail query failed session_id=%s", session_id)
            raise self._internal_error("Failed to load driving session.") from exc

        return self._to_detail_response(driving_session, summary)

    async def end_session(
        self,
        account: Account,
        session_id: str,
        request: DrivingSessionEndRequest,
    ) -> DrivingSessionEndResponse:
        try:
            driving_session = await self.driving_session_repository.get_owned_by_account_for_update(
                account_id=account.id,
                session_id=session_id,
            )
            if driving_session is None:
                raise self._session_not_found()

            if driving_session.status != DrivingSessionStatus.ACTIVE.value:
                raise self._session_not_active()

            ended_at = utc_now_for_mysql_datetime()
            location_samples = await self.location_sample_repository.list_coordinates_by_session(
                driving_session.id,
            )
            end_coordinate = self._request_coordinate(request)
            distance_meters = self._calculate_distance(
                driving_session,
                location_samples,
                end_coordinate,
            )
            duration_seconds = max(
                0,
                int((ended_at - driving_session.started_at).total_seconds()),
            )
            average_speed_kph = self._calculate_average_speed(distance_meters, duration_seconds)

            driving_session.status = self._end_status_for_reason(request.end_reason)
            driving_session.end_reason = request.end_reason
            driving_session.ended_at = ended_at
            driving_session.end_latitude = (
                None if end_coordinate is None else end_coordinate.latitude
            )
            driving_session.end_longitude = (
                None if end_coordinate is None else end_coordinate.longitude
            )
            driving_session.distance_meters = distance_meters
            driving_session.duration_seconds = duration_seconds
            driving_session.average_speed_kph = average_speed_kph
            driving_session.safety_score = None

            await self.driving_session_repository.close_active_behavior_events(
                session_id=driving_session.id,
                ended_at=ended_at,
            )
            await self.driving_session_repository.cancel_open_interventions(
                session_id=driving_session.id,
                ended_at=ended_at,
            )
            await self.driving_session_repository.abort_active_conversations(
                session_id=driving_session.id,
                ended_at=ended_at,
            )
            await self.session.flush()
            await self.session.refresh(driving_session)
            summary = await self.summary_repository.get_summary(driving_session.id)
            await self.session.commit()
            return DrivingSessionEndResponse(
                **self._to_detail_response(driving_session, summary).model_dump(),
            )
        except AppException:
            await self.session.rollback()
            raise
        except IntegrityError as exc:
            await self.session.rollback()
            logger.exception("Driving session end integrity error session_id=%s", session_id)
            raise self._internal_error("Failed to end driving session.") from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Driving session end database error session_id=%s", session_id)
            raise self._internal_error("Failed to end driving session.") from exc

    async def list_history(
        self,
        account: Account,
        profile_id: str,
        *,
        page: int = DEFAULT_DRIVING_SESSION_PAGE,
        size: int = DEFAULT_DRIVING_SESSION_SIZE,
        status_filter: str | None = None,
        started_from: str | None = None,
        started_to: str | None = None,
    ) -> DrivingSessionHistoryResponse:
        self._validate_pagination(page, size)
        normalized_status = self._validate_status_filter(status_filter)
        started_from_datetime, started_to_datetime = self._parse_date_range(
            started_from=started_from,
            started_to=started_to,
        )

        try:
            profile = await self.profile_repository.get_by_account(account.id, profile_id)
            if profile is None:
                raise self._profile_not_found()

            total = await self.driving_session_repository.count_by_profile(
                profile_id=profile.id,
                status_filter=normalized_status,
                started_from=started_from_datetime,
                started_to_exclusive=started_to_datetime,
            )
            sessions = await self.driving_session_repository.list_by_profile(
                profile_id=profile.id,
                page=page,
                size=size,
                status_filter=normalized_status,
                started_from=started_from_datetime,
                started_to_exclusive=started_to_datetime,
            )
        except AppException:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Driving session history query failed profile_id=%s", profile_id)
            raise self._internal_error("Failed to load driving session history.") from exc

        return DrivingSessionHistoryResponse.from_items(
            items=[
                self._to_history_item_response(driving_session, behavior_event_count)
                for driving_session, behavior_event_count in sessions
            ],
            page=page,
            size=size,
            total=total,
        )

    @staticmethod
    def _validate_pagination(page: int, size: int) -> None:
        if page < 1:
            raise AppException(
                "Page must be greater than or equal to 1.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                error_code=ErrorCode.INVALID_PAGE,
            )

        if size < 1 or size > MAX_DRIVING_SESSION_SIZE:
            raise AppException(
                "Page size must be between 1 and 100.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                error_code=ErrorCode.INVALID_PAGE_SIZE,
            )

    @staticmethod
    def _validate_status_filter(status_filter: str | None) -> str | None:
        if status_filter is None:
            return None

        if status_filter not in {item.value for item in DrivingSessionStatus}:
            raise AppException(
                "Driving session status is invalid.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                error_code=ErrorCode.INVALID_SESSION_STATUS,
            )
        return status_filter

    @classmethod
    def _parse_date_range(
        cls,
        *,
        started_from: str | None,
        started_to: str | None,
    ) -> tuple[datetime | None, datetime | None]:
        from_date = cls._parse_date_filter(started_from)
        to_date = cls._parse_date_filter(started_to)

        if from_date is not None and to_date is not None and from_date > to_date:
            raise cls._invalid_date_range()

        started_from_datetime = (
            None if from_date is None else datetime.combine(from_date, time.min)
        )
        started_to_datetime = (
            None
            if to_date is None
            else datetime.combine(to_date + timedelta(days=1), time.min)
        )
        return started_from_datetime, started_to_datetime

    @classmethod
    def _parse_date_filter(cls, value: str | None) -> date | None:
        if value is None:
            return None

        if len(value) != 10:
            raise cls._invalid_date_range()

        try:
            parsed_date = date.fromisoformat(value)
        except ValueError as exc:
            raise cls._invalid_date_range() from exc

        if value != parsed_date.isoformat():
            raise cls._invalid_date_range()
        return parsed_date

    @staticmethod
    def _end_status_for_reason(end_reason: str) -> str:
        if end_reason == SessionEndReason.USER_REQUEST.value:
            return DrivingSessionStatus.COMPLETED.value
        return DrivingSessionStatus.ABORTED.value

    @staticmethod
    def _calculate_average_speed(distance_meters: int, duration_seconds: int) -> Decimal:
        if duration_seconds == 0:
            return Decimal("0.00")
        return Decimal(str(round(distance_meters / duration_seconds * 3.6, 2)))

    @classmethod
    def _calculate_distance(
        cls,
        driving_session: DrivingSession,
        location_samples: list[Coordinate],
        end_coordinate: Coordinate | None,
    ) -> int:
        points: list[Coordinate] = []
        start_coordinate = cls._model_coordinate(
            driving_session.start_latitude,
            driving_session.start_longitude,
        )
        if start_coordinate is not None:
            points.append(start_coordinate)
        points.extend(location_samples)
        if end_coordinate is not None:
            points.append(end_coordinate)
        return total_distance_meters(points)

    @staticmethod
    def _request_coordinate(request: DrivingSessionEndRequest) -> Coordinate | None:
        if request.end_location is None:
            return None
        return Coordinate(
            latitude=request.end_location.latitude,
            longitude=request.end_location.longitude,
        )

    @staticmethod
    def _model_coordinate(latitude: float | None, longitude: float | None) -> Coordinate | None:
        if latitude is None or longitude is None:
            return None
        return Coordinate(latitude=float(latitude), longitude=float(longitude))

    def _to_start_response(self, driving_session: DrivingSession) -> DrivingSessionStartResponse:
        start_location = self._coordinate_response(
            driving_session.start_latitude,
            driving_session.start_longitude,
        )
        assert start_location is not None
        return DrivingSessionStartResponse(
            id=driving_session.id,
            profile_id=driving_session.profile_id,
            status=driving_session.status,
            started_at=driving_session.started_at,
            start_location=start_location,
            destination=self._start_destination_response(driving_session),
            model_version=driving_session.model_version,
            policy_version=driving_session.policy_version,
            web_socket_url=self._web_socket_url(driving_session.id),
        )

    def _to_active_response(self, driving_session: DrivingSession) -> ActiveDrivingSessionResponse:
        return ActiveDrivingSessionResponse(
            id=driving_session.id,
            profile_id=driving_session.profile_id,
            status=driving_session.status,
            started_at=driving_session.started_at,
            destination_name=driving_session.destination_name,
            model_version=driving_session.model_version,
            policy_version=driving_session.policy_version,
            web_socket_url=self._web_socket_url(driving_session.id),
        )

    def _to_detail_response(
        self,
        driving_session: DrivingSession,
        summary: SessionSummary,
    ) -> DrivingSessionDetailResponse:
        return DrivingSessionDetailResponse(
            id=driving_session.id,
            profile_id=driving_session.profile_id,
            status=driving_session.status,
            end_reason=driving_session.end_reason,
            started_at=driving_session.started_at,
            ended_at=driving_session.ended_at,
            start_location=self._coordinate_response(
                driving_session.start_latitude,
                driving_session.start_longitude,
            ),
            end_location=self._coordinate_response(
                driving_session.end_latitude,
                driving_session.end_longitude,
            ),
            destination_name=driving_session.destination_name,
            distance_meters=driving_session.distance_meters,
            duration_seconds=driving_session.duration_seconds,
            average_speed_kph=self._decimal_to_float(driving_session.average_speed_kph),
            safety_score=driving_session.safety_score,
            model_version=driving_session.model_version,
            policy_version=driving_session.policy_version,
            summary=self._summary_response(summary),
        )

    @classmethod
    def _to_history_item_response(
        cls,
        driving_session: DrivingSession,
        behavior_event_count: int,
    ) -> DrivingSessionHistoryItemResponse:
        return DrivingSessionHistoryItemResponse(
            id=driving_session.id,
            status=driving_session.status,
            started_at=driving_session.started_at,
            ended_at=driving_session.ended_at,
            destination_name=driving_session.destination_name,
            distance_meters=driving_session.distance_meters,
            duration_seconds=driving_session.duration_seconds,
            average_speed_kph=cls._decimal_to_float(driving_session.average_speed_kph),
            safety_score=driving_session.safety_score,
            behavior_event_count=behavior_event_count,
        )

    @staticmethod
    def _coordinate_response(
        latitude: float | None,
        longitude: float | None,
    ) -> CoordinateResponse | None:
        if latitude is None or longitude is None:
            return None
        return CoordinateResponse(latitude=float(latitude), longitude=float(longitude))

    @staticmethod
    def _start_destination_response(
        driving_session: DrivingSession,
    ) -> SessionStartDestinationResponse | None:
        if driving_session.destination_name is None:
            return None
        return SessionStartDestinationResponse(
            provider_place_id=driving_session.destination_place_id,
            name=driving_session.destination_name,
        )

    @staticmethod
    def _summary_response(summary: SessionSummary) -> DrivingSessionSummaryResponse:
        correction_rate = (
            0.0
            if summary.intervention_count == 0
            else round(
                summary.corrected_behavior_count / summary.intervention_count * 100,
                1,
            )
        )
        return DrivingSessionSummaryResponse(
            behavior_event_count=summary.behavior_event_count,
            intervention_count=summary.intervention_count,
            corrected_behavior_count=summary.corrected_behavior_count,
            behavior_correction_rate=correction_rate,
            average_response_latency_ms=summary.average_response_latency_ms,
        )

    @staticmethod
    def _decimal_to_float(value: Decimal | None) -> float | None:
        return None if value is None else float(value)

    def _web_socket_url(self, session_id: str) -> str:
        return f"{self.settings.ws_v1_prefix}/driving-sessions/{session_id}"

    @staticmethod
    def _profile_not_found() -> AppException:
        return AppException(
            "Driver profile was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=ErrorCode.PROFILE_NOT_FOUND,
        )

    @staticmethod
    def _session_not_found() -> AppException:
        return AppException(
            "Driving session was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=ErrorCode.SESSION_NOT_FOUND,
        )

    @staticmethod
    def _session_not_active() -> AppException:
        return AppException(
            "Driving session is not active.",
            status_code=status.HTTP_409_CONFLICT,
            error_code=ErrorCode.SESSION_NOT_ACTIVE,
        )

    @staticmethod
    def _active_session_exists() -> AppException:
        return AppException(
            "An active driving session already exists.",
            status_code=status.HTTP_409_CONFLICT,
            error_code=ErrorCode.ACTIVE_SESSION_EXISTS,
        )

    @staticmethod
    def _model_not_available() -> AppException:
        return AppException(
            "Driver monitoring model is not available.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=ErrorCode.MODEL_NOT_AVAILABLE,
        )

    @staticmethod
    def _invalid_date_range() -> AppException:
        return AppException(
            "Driving session date range is invalid.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code=ErrorCode.INVALID_DATE_RANGE,
        )

    @staticmethod
    def _internal_error(message: str) -> AppException:
        return AppException(
            message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
        )
