import logging

from fastapi import APIRouter, File, UploadFile, status

from app.api.dependencies import AppSettings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.integrations.gemini.manual_risk_voice import (
    GeminiManualRiskVoiceClient,
    GeminiNotConfiguredError,
    GeminiProviderError,
)
from app.schemas.manual_risk_voice import (
    ManualRiskVoiceMatchRequest,
    ManualRiskVoiceMatchResponse,
    ManualRiskVoiceTranscriptionResponse,
)
from app.services.manual_risk_voice_service import ManualRiskVoiceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/manual-risk/voice", tags=["manual-risk-voice"])
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.post("/transcriptions", response_model=ManualRiskVoiceTranscriptionResponse)
async def transcribe_manual_risk_voice(
    settings: AppSettings,
    audio: UploadFile = File(...),  # noqa: B008
) -> ManualRiskVoiceTranscriptionResponse:
    mime_type = (audio.content_type or "").strip().lower()
    content = await audio.read()
    if not mime_type.startswith("audio/") or not content:
        raise AppException(
            "유효한 음성 파일을 보내 주세요.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code=ErrorCode.INVALID_MANUAL_RISK_VOICE_AUDIO,
        )
    if len(content) > MAX_AUDIO_BYTES:
        raise AppException(
            "음성 파일은 10MB 이하여야 합니다.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            error_code=ErrorCode.INVALID_MANUAL_RISK_VOICE_AUDIO,
        )

    service = ManualRiskVoiceService(
        gemini_client=GeminiManualRiskVoiceClient(settings=settings)
    )
    try:
        transcript = await service.transcribe(audio=content, mime_type=mime_type)
    except GeminiNotConfiguredError as exc:
        raise AppException(
            "Gemini 음성 인식 설정이 완료되지 않았습니다.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=ErrorCode.GEMINI_MANUAL_RISK_VOICE_NOT_CONFIGURED,
        ) from exc
    except GeminiProviderError as exc:
        logger.warning("Gemini manual risk transcription failed reason=%s", exc.reason)
        raise AppException(
            "음성을 인식하지 못했습니다. 다시 말씀해 주세요.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code=ErrorCode.GEMINI_MANUAL_RISK_VOICE_FAILED,
        ) from exc
    finally:
        await audio.close()
    return ManualRiskVoiceTranscriptionResponse(transcript=transcript)


@router.post("/matches", response_model=ManualRiskVoiceMatchResponse)
async def match_manual_risk_voice(
    payload: ManualRiskVoiceMatchRequest,
    settings: AppSettings,
) -> ManualRiskVoiceMatchResponse:
    service = ManualRiskVoiceService(
        gemini_client=GeminiManualRiskVoiceClient(settings=settings)
    )
    try:
        option_id = await service.match(transcript=payload.transcript, options=payload.options)
    except GeminiNotConfiguredError as exc:
        raise AppException(
            "Gemini 음성 인식 설정이 완료되지 않았습니다.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=ErrorCode.GEMINI_MANUAL_RISK_VOICE_NOT_CONFIGURED,
        ) from exc
    except GeminiProviderError as exc:
        logger.warning("Gemini manual risk match failed reason=%s", exc.reason)
        raise AppException(
            "음성 요청을 분류하지 못했습니다. 다시 말씀해 주세요.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code=ErrorCode.GEMINI_MANUAL_RISK_VOICE_FAILED,
        ) from exc
    return ManualRiskVoiceMatchResponse(option_id=option_id)
