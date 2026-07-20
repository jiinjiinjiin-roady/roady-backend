from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.enums import BehaviorType, DrivingState

HIGH_BASE_RISK_BEHAVIORS = {
    BehaviorType.DROWSINESS.value,
    BehaviorType.PHONE_USE.value,
    BehaviorType.GAZE_AWAY.value,
}


@dataclass(frozen=True, slots=True)
class BehaviorRiskInput:
    behavior_type: str
    average_confidence: Decimal
    driving_state: str
    speed_kph: Decimal | None
    recurrence_count: int


def calculate_behavior_risk_level(value: BehaviorRiskInput) -> int:
    base_level = 2 if value.behavior_type in HIGH_BASE_RISK_BEHAVIORS else 1
    moving_boost = 1 if value.driving_state == DrivingState.MOVING.value else 0
    speed_boost = 1 if value.speed_kph is not None and value.speed_kph >= Decimal("60") else 0
    confidence_boost = 1 if value.average_confidence >= Decimal("0.8500") else 0
    recurrence_boost = 1 if value.recurrence_count >= 2 else 0

    raw_level = base_level + moving_boost + speed_boost + confidence_boost + recurrence_boost
    if value.driving_state == DrivingState.PARKED.value:
        raw_level -= 1

    return max(1, min(3, raw_level))
