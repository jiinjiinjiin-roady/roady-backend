from decimal import Decimal

from app.core.enums import BehaviorType, DrivingState
from app.policies.behavior_risk_policy import BehaviorRiskInput, calculate_behavior_risk_level


def test_moving_high_confidence_phone_use_reaches_high_risk() -> None:
    risk_level = calculate_behavior_risk_level(
        BehaviorRiskInput(
            behavior_type=BehaviorType.PHONE_USE.value,
            average_confidence=Decimal("0.9000"),
            driving_state=DrivingState.MOVING.value,
            speed_kph=Decimal("42.30"),
            recurrence_count=0,
        )
    )

    assert risk_level == 3


def test_repeated_lower_base_behavior_escalates_with_speed_and_recurrence() -> None:
    risk_level = calculate_behavior_risk_level(
        BehaviorRiskInput(
            behavior_type=BehaviorType.FOOD_OR_DRINK.value,
            average_confidence=Decimal("0.8000"),
            driving_state=DrivingState.MOVING.value,
            speed_kph=Decimal("70.00"),
            recurrence_count=2,
        )
    )

    assert risk_level == 3


def test_parked_behavior_keeps_minimum_risk_floor() -> None:
    risk_level = calculate_behavior_risk_level(
        BehaviorRiskInput(
            behavior_type=BehaviorType.SMOKING.value,
            average_confidence=Decimal("0.7600"),
            driving_state=DrivingState.PARKED.value,
            speed_kph=Decimal("0.00"),
            recurrence_count=0,
        )
    )

    assert risk_level == 1
