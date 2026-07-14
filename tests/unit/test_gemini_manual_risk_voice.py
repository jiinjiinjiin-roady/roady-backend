import base64
import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.gemini.manual_risk_voice import (
    GeminiManualRiskVoiceClient,
    GeminiNotConfiguredError,
    GeminiProviderError,
)


def make_settings(**overrides: object) -> Settings:
    values = {"gemini_api_key": "test-api-key", "gemini_model": "gemini-2.5-flash"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_transcribe_sends_inline_audio_and_returns_strict_transcript() -> None:
    captured_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-api-key"
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "창문 좀 열어줘"}]}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        transcript = await GeminiManualRiskVoiceClient(
            settings=make_settings(), client=http_client
        ).transcribe(audio=b"audio-bytes", mime_type="audio/webm")

    assert transcript == "창문 좀 열어줘"
    part = captured_payload["contents"][0]["parts"][1]  # type: ignore[index]
    assert part == {
        "inlineData": {
            "mimeType": "audio/webm",
            "data": base64.b64encode(b"audio-bytes").decode("ascii"),
        }
    }


@pytest.mark.asyncio
async def test_match_returns_only_an_id_supplied_by_the_current_ui() -> None:
    options = [
        {"id": "window", "label": "창문 열기"},
        {"id": "music", "label": "밝은 음악 재생"},
    ]

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"optionId":"window"}'}]}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        option_id = await GeminiManualRiskVoiceClient(
            settings=make_settings(), client=http_client
        ).match(transcript="창문 좀 열어줘", options=options)

    assert option_id == "window"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_text",
    ['{"optionId":"untrusted"}', '{"optionId":null}', "not json"],
)
async def test_match_treats_unrecognised_or_no_match_output_as_none(response_text: str) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": response_text}]}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        option_id = await GeminiManualRiskVoiceClient(
            settings=make_settings(), client=http_client
        ).match(
            transcript="무언가 해줘",
            options=[{"id": "window", "label": "창문 열기"}],
        )

    assert option_id is None


@pytest.mark.asyncio
async def test_voice_client_maps_timeout_to_provider_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GeminiManualRiskVoiceClient(settings=make_settings(), client=http_client)
        with pytest.raises(GeminiProviderError, match="request failed") as exc_info:
            await client.transcribe(audio=b"audio", mime_type="audio/webm")

    assert exc_info.value.reason == "request_timeout"


@pytest.mark.asyncio
async def test_voice_client_requires_existing_gemini_configuration() -> None:
    client = GeminiManualRiskVoiceClient(settings=make_settings(gemini_api_key=""))

    with pytest.raises(GeminiNotConfiguredError, match="GEMINI_API_KEY"):
        await client.match(
            transcript="창문 열어줘",
            options=[{"id": "window", "label": "창문 열기"}],
        )
