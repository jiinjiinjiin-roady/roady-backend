import base64
import json
import logging
from collections.abc import Mapping, Sequence

import httpx

from app.core.config import Settings

GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
logger = logging.getLogger(__name__)

MATCH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"optionId": {"type": ["string", "null"]}},
    "required": ["optionId"],
    "additionalProperties": False,
    "propertyOrdering": ["optionId"],
}


class GeminiNotConfiguredError(RuntimeError):
    pass


class GeminiProviderError(RuntimeError):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


class GeminiManualRiskVoiceClient:
    def __init__(
        self,
        *,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    async def transcribe(self, *, audio: bytes, mime_type: str) -> str:
        api_key, model = self._required_settings()
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "전달된 오디오의 한국어 음성만 정확히 전사하세요. "
                            "설명, 번역, 화자 표기, 따옴표를 추가하지 말고 "
                            "전사 텍스트만 반환하세요."
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "다음 오디오를 전사하세요."},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64.b64encode(audio).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
        }
        response_data = await self._request(model=model, api_key=api_key, payload=payload)
        transcript = _extract_response_text(response_data).strip()
        if not transcript:
            raise GeminiProviderError(
                "Gemini returned an invalid manual risk transcription response.",
                reason="empty_transcript",
            )
        return transcript

    async def match(
        self,
        *,
        transcript: str,
        options: Sequence[Mapping[str, str]],
    ) -> str | None:
        api_key, model = self._required_settings()
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "운전자의 발화를 제공된 선택지 중 정확히 하나의 id로 분류하세요. "
                            "제공되지 않은 행동을 추론하지 말고 애매하거나 일치하지 않으면 "
                            "optionId에 null을 반환하세요."
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {"transcript": transcript, "options": list(options)},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseFormat": {
                    "text": {"mimeType": "APPLICATION_JSON", "schema": MATCH_RESPONSE_SCHEMA}
                }
            },
        }
        response_data = await self._request(model=model, api_key=api_key, payload=payload)
        return parse_manual_risk_match_response(response_data, {option["id"] for option in options})

    def _required_settings(self) -> tuple[str, str]:
        api_key = self._settings.gemini_api_key.strip()
        model = self._settings.gemini_model.strip()
        missing = [
            name
            for name, value in (("GEMINI_API_KEY", api_key), ("GEMINI_MODEL", model))
            if not value
        ]
        if missing:
            raise GeminiNotConfiguredError(
                f"Required Gemini configuration is missing: {', '.join(missing)}."
            )
        return api_key, model

    async def _request(
        self,
        *,
        model: str,
        api_key: str,
        payload: dict[str, object],
    ) -> object:
        try:
            response = await self._generate_content(model=model, api_key=api_key, payload=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "Gemini manual risk voice request failed reason=request_timeout timeout_seconds=%s",
                self._settings.gemini_request_timeout_seconds,
            )
            raise GeminiProviderError(
                "Gemini manual risk voice request failed.", reason="request_timeout"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Gemini manual risk voice request failed reason=http_status status_code=%s",
                exc.response.status_code,
            )
            raise GeminiProviderError(
                "Gemini manual risk voice request failed.", reason="http_status"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Gemini manual risk voice request failed reason=transport_error exception_type=%s",
                type(exc).__name__,
            )
            raise GeminiProviderError(
                "Gemini manual risk voice request failed.", reason="transport_error"
            ) from exc
        except ValueError as exc:
            logger.warning(
                "Gemini manual risk voice request failed "
                "reason=response_json_decode exception_type=%s",
                type(exc).__name__,
            )
            raise GeminiProviderError(
                "Gemini manual risk voice request failed.", reason="response_json_decode"
            ) from exc

    async def _generate_content(
        self,
        *,
        model: str,
        api_key: str,
        payload: dict[str, object],
    ) -> httpx.Response:
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model)
        headers = {"x-goog-api-key": api_key}
        if self._client is not None:
            return await self._client.post(url, headers=headers, json=payload)

        async with httpx.AsyncClient(
            timeout=self._settings.gemini_request_timeout_seconds
        ) as client:
            return await client.post(url, headers=headers, json=payload)


def parse_manual_risk_match_response(value: object, option_ids: set[str]) -> str | None:
    try:
        payload = json.loads(_strip_complete_json_fence(_extract_response_text(value)))
    except (TypeError, ValueError, GeminiProviderError):
        return None

    if not isinstance(payload, dict) or set(payload) != {"optionId"}:
        return None
    option_id = payload["optionId"]
    if option_id is None:
        return None
    if not isinstance(option_id, str) or option_id not in option_ids:
        return None
    return option_id


def _extract_response_text(value: object) -> str:
    if not isinstance(value, Mapping):
        raise _invalid_response("candidate_missing")
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise _invalid_response("candidate_missing")
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        raise _invalid_response("candidate_missing")
    content = candidate.get("content")
    if not isinstance(content, Mapping):
        raise _invalid_response("parts_missing")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise _invalid_response("parts_missing")
    texts = [part.get("text") for part in parts if isinstance(part, Mapping)]
    if len(texts) != len(parts) or not all(isinstance(text, str) for text in texts):
        raise _invalid_response("parts_missing")
    return "".join(texts)


def _strip_complete_json_fence(text: str) -> str:
    prefix = "```json\n"
    suffix = "\n```"
    if text.startswith(prefix) and text.endswith(suffix):
        return text[len(prefix) : -len(suffix)]
    return text


def _invalid_response(reason: str) -> GeminiProviderError:
    return GeminiProviderError("Gemini manual risk voice response is invalid.", reason=reason)
