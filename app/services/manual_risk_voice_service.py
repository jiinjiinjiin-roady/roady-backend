from collections.abc import Sequence

from app.integrations.gemini.manual_risk_voice import GeminiManualRiskVoiceClient
from app.schemas.manual_risk_voice import ManualRiskVoiceOption


class ManualRiskVoiceService:
    def __init__(self, *, gemini_client: GeminiManualRiskVoiceClient) -> None:
        self._gemini_client = gemini_client

    async def transcribe(self, *, audio: bytes, mime_type: str) -> str:
        return await self._gemini_client.transcribe(audio=audio, mime_type=mime_type)

    async def match(
        self, *, transcript: str, options: Sequence[ManualRiskVoiceOption]
    ) -> str | None:
        return await self._gemini_client.match(
            transcript=transcript,
            options=[option.model_dump() for option in options],
        )
