from collections.abc import Sequence

from app.integrations.gemini.manual_risk_voice import (
    GeminiManualRiskVoiceClient,
    GeminiNotConfiguredError,
    GeminiProviderError,
)
from app.policies.demo_fallback_policy import fallback_manual_risk_option_id
from app.schemas.manual_risk_voice import ManualRiskVoiceOption


class ManualRiskVoiceService:
    def __init__(self, *, gemini_client: GeminiManualRiskVoiceClient) -> None:
        self._gemini_client = gemini_client

    async def transcribe(self, *, audio: bytes, mime_type: str) -> str:
        return await self._gemini_client.transcribe(audio=audio, mime_type=mime_type)

    async def match(
        self, *, transcript: str, options: Sequence[ManualRiskVoiceOption]
    ) -> str | None:
        option_payload = [option.model_dump() for option in options]
        try:
            return await self._gemini_client.match(
                transcript=transcript,
                options=option_payload,
            )
        except (GeminiNotConfiguredError, GeminiProviderError):
            return fallback_manual_risk_option_id(
                transcript=transcript,
                options=option_payload,
            )
