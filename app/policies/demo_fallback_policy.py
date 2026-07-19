from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.core.enums import BehaviorType

DEMO_FALLBACK_MUSIC_TRACKS: dict[str, list[dict[str, object]]] = {
    "bright": [
        {
            "id": "demo-fallback-bright-road",
            "title": "Bright Road",
            "artist": "Roady Session",
            "album": "Wake Drive",
            "duration": "2:58",
            "durationSeconds": 178,
            "coverUrl": None,
            "sourceUrl": "",
            "provider": "demo-fallback",
        },
        {
            "id": "demo-fallback-soft-focus",
            "title": "Soft Focus",
            "artist": "Evening Route",
            "album": "Bright Pop Drive",
            "duration": "3:08",
            "durationSeconds": 188,
            "coverUrl": None,
            "sourceUrl": "",
            "provider": "demo-fallback",
        },
    ],
    "calm": [
        {
            "id": "demo-fallback-calm-lane",
            "title": "Calm Lane",
            "artist": "Roady Session",
            "album": "Quiet Route",
            "duration": "3:32",
            "durationSeconds": 212,
            "coverUrl": None,
            "sourceUrl": "",
            "provider": "demo-fallback",
        }
    ],
    "drive": [
        {
            "id": "demo-fallback-drive-neon",
            "title": "Drive Neon",
            "artist": "Roady Session",
            "album": "City Pulse",
            "duration": "3:24",
            "durationSeconds": 204,
            "coverUrl": None,
            "sourceUrl": "",
            "provider": "demo-fallback",
        },
        {
            "id": "demo-fallback-red-sunset",
            "title": "붉은 노을",
            "artist": "Drive Mix",
            "album": "Road Trip",
            "duration": "3:26",
            "durationSeconds": 206,
            "coverUrl": None,
            "sourceUrl": "",
            "provider": "demo-fallback",
        },
    ],
    "focus": [
        {
            "id": "demo-fallback-focus-loop",
            "title": "Focus Loop",
            "artist": "Roady Session",
            "album": "Steady Hands",
            "duration": "3:46",
            "durationSeconds": 226,
            "coverUrl": None,
            "sourceUrl": "",
            "provider": "demo-fallback",
        }
    ],
}

MANUAL_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "window": ("창문", "창", "환기", "열어", "열기"),
    "music": ("음악", "노래", "틀어", "재생", "신나는", "밝은"),
    "message": ("문자", "메시지", "연락", "보내", "전송"),
    "route": ("경로", "길", "우회", "목적지", "안내"),
    "place": ("장소", "근처", "찾아", "검색"),
    "stop": ("그만", "취소", "닫아", "멈춰", "중지"),
}


def fallback_music_recommendations(*, mood: str, limit: int) -> list[dict[str, object]]:
    tracks = DEMO_FALLBACK_MUSIC_TRACKS.get(
        mood.strip().lower(), DEMO_FALLBACK_MUSIC_TRACKS["drive"]
    )
    safe_limit = max(1, limit)
    return [dict(track) for track in tracks[:safe_limit]]


def fallback_manual_risk_option_id(
    *,
    transcript: str,
    options: Sequence[Mapping[str, str]],
) -> str | None:
    normalized_transcript = _normalize_match_text(transcript)
    if not normalized_transcript:
        return None

    best_option_id: str | None = None
    best_score = 0
    for option in options:
        option_id = str(option.get("id", "")).strip()
        label = str(option.get("label", "")).strip()
        if not option_id or not label:
            continue

        score = _score_manual_risk_option(
            normalized_transcript=normalized_transcript,
            normalized_label=_normalize_match_text(label),
            option_id=option_id.lower(),
        )
        if score > best_score:
            best_score = score
            best_option_id = option_id

    return best_option_id if best_score >= 2 else None


def fallback_behavior_warning_sensitivity(
    *,
    current: Mapping[str, int],
    telemetry_events: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    recommendation = {behavior.value: int(current[behavior.value]) for behavior in BehaviorType}
    for event in telemetry_events:
        behavior_type = str(event.get("behaviorType") or event.get("behavior_type") or "")
        if behavior_type not in recommendation:
            continue

        level = _safe_int(event.get("level"))
        click_count = _safe_int(event.get("clickCount") or event.get("click_count"))
        delta = _behavior_sensitivity_delta(level=level, click_count=click_count)
        recommendation[behavior_type] = _clamp_sensitivity(recommendation[behavior_type] + delta)

    return recommendation


def _score_manual_risk_option(
    *,
    normalized_transcript: str,
    normalized_label: str,
    option_id: str,
) -> int:
    if normalized_label and (
        normalized_label in normalized_transcript or normalized_transcript in normalized_label
    ):
        return 10

    score = 0
    for keyword in MANUAL_RISK_KEYWORDS.get(option_id, ()):
        if _normalize_match_text(keyword) in normalized_transcript:
            score += 2

    for token in _meaningful_tokens(normalized_label):
        if token in normalized_transcript:
            score += 1

    return score


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", value).lower()


def _meaningful_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[0-9a-zA-Z가-힣]+", value.lower())
        if len(token) >= 2
    ]


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _behavior_sensitivity_delta(*, level: int, click_count: int) -> int:
    if level >= 3 or click_count >= 3:
        return 1
    if level <= 1 and click_count == 0:
        return -1
    return 0


def _clamp_sensitivity(value: int) -> int:
    return max(3, min(10, value))
