from app.integrations.gemini.manual_risk_voice import (
    GeminiNotConfiguredError,
    GeminiProviderError,
)
from app.schemas.manual_risk_voice import ManualRiskVoiceOption
from app.services.manual_risk_voice_service import ManualRiskVoiceService


class NotConfiguredGeminiClient:
    async def match(self, **_: object) -> str | None:
        raise GeminiNotConfiguredError("missing configuration")


class FailingGeminiClient:
    async def match(self, **_: object) -> str | None:
        raise GeminiProviderError("provider failed", reason="request_timeout")


async def test_match_returns_rule_based_backend_fallback_when_gemini_is_not_configured() -> None:
    service = ManualRiskVoiceService(
        gemini_client=NotConfiguredGeminiClient(),  # type: ignore[arg-type]
    )

    option_id = await service.match(
        transcript="창문을 좀 열어줘",
        options=[
            ManualRiskVoiceOption(id="window", label="창문 열기"),
            ManualRiskVoiceOption(id="music", label="음악 재생"),
        ],
    )

    assert option_id == "window"


async def test_match_returns_rule_based_backend_fallback_when_gemini_fails() -> None:
    service = ManualRiskVoiceService(
        gemini_client=FailingGeminiClient(),  # type: ignore[arg-type]
    )

    option_id = await service.match(
        transcript="신나는 노래 틀어줘",
        options=[
            ManualRiskVoiceOption(id="window", label="창문 열기"),
            ManualRiskVoiceOption(id="music", label="음악 재생"),
        ],
    )

    assert option_id == "music"


async def test_match_returns_none_when_rule_based_backend_fallback_cannot_match() -> None:
    service = ManualRiskVoiceService(
        gemini_client=FailingGeminiClient(),  # type: ignore[arg-type]
    )

    option_id = await service.match(
        transcript="오늘 날씨가 어때",
        options=[
            ManualRiskVoiceOption(id="window", label="창문 열기"),
            ManualRiskVoiceOption(id="music", label="음악 재생"),
        ],
    )

    assert option_id is None
