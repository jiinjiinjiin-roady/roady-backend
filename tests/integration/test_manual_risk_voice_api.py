import pytest

from app.integrations.gemini.manual_risk_voice import (
    GeminiNotConfiguredError,
    GeminiProviderError,
)


@pytest.mark.asyncio
async def test_manual_risk_voice_endpoints_validate_their_public_contract(client) -> None:
    missing_audio = await client.post("/api/v1/manual-risk/voice/transcriptions")
    invalid_match = await client.post(
        "/api/v1/manual-risk/voice/matches",
        json={"transcript": " ", "options": []},
    )

    assert missing_audio.status_code == 422
    assert invalid_match.status_code == 422


@pytest.mark.asyncio
async def test_transcription_returns_service_transcript(client, monkeypatch) -> None:
    class FakeService:
        def __init__(self, **_: object) -> None:
            pass

        async def transcribe(self, *, audio: bytes, mime_type: str) -> str:
            assert audio == b"voice-bytes"
            assert mime_type == "audio/webm"
            return "창문 좀 열어줘"

    monkeypatch.setattr(
        "app.api.v1.endpoints.manual_risk_voice.ManualRiskVoiceService", FakeService
    )
    response = await client.post(
        "/api/v1/manual-risk/voice/transcriptions",
        files={"audio": ("voice.webm", b"voice-bytes", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "창문 좀 열어줘"}


@pytest.mark.asyncio
async def test_match_maps_gemini_configuration_failure_to_503(client, monkeypatch) -> None:
    class FakeService:
        def __init__(self, **_: object) -> None:
            pass

        async def match(self, **_: object) -> str | None:
            raise GeminiNotConfiguredError("missing configuration")

    monkeypatch.setattr(
        "app.api.v1.endpoints.manual_risk_voice.ManualRiskVoiceService", FakeService
    )
    response = await client.post(
        "/api/v1/manual-risk/voice/matches",
        json={
            "transcript": "창문을 열어줘",
            "options": [{"id": "window", "label": "창문 열기"}],
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == "GEMINI_MANUAL_RISK_VOICE_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_manual_risk_match_maps_gemini_provider_failure_to_502(client, monkeypatch) -> None:
    class FakeService:
        def __init__(self, **_: object) -> None:
            pass

        async def match(self, **_: object) -> str | None:
            raise GeminiProviderError("provider failed", reason="request_timeout")

    monkeypatch.setattr(
        "app.api.v1.endpoints.manual_risk_voice.ManualRiskVoiceService", FakeService
    )
    response = await client.post(
        "/api/v1/manual-risk/voice/matches",
        json={
            "transcript": "창문을 열어줘",
            "options": [{"id": "window", "label": "창문 열기"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["error"] == "GEMINI_MANUAL_RISK_VOICE_FAILED"
