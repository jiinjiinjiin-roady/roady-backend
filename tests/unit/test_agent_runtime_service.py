from types import SimpleNamespace

from app.core.enums import DriverResponseType
from app.services.agent_runtime_service import AgentRuntimeService


def test_response_personalization_increases_sensitivity_on_repeated_behavior() -> None:
    profile = SimpleNamespace(
        behavior_warning_sensitivity={
            "DROWSINESS": 9,
            "PHONE_USE": 9,
            "FOOD_OR_DRINK": 7,
            "GAZE_AWAY": 9,
            "SECONDARY_TASK": 7,
            "REACHING_BEHIND": 7,
            "SMOKING": 7,
        }
    )

    AgentRuntimeService._apply_response_personalization(
        profile=profile,
        behavior_type="FOOD_OR_DRINK",
        response_type=DriverResponseType.BEHAVIOR_REPEATED,
        behavior_corrected=False,
    )

    assert profile.behavior_warning_sensitivity["FOOD_OR_DRINK"] == 8


def test_response_personalization_decreases_sensitivity_on_effective_intervention() -> None:
    profile = SimpleNamespace(
        behavior_warning_sensitivity={
            "DROWSINESS": 9,
            "PHONE_USE": 9,
            "FOOD_OR_DRINK": 7,
            "GAZE_AWAY": 9,
            "SECONDARY_TASK": 7,
            "REACHING_BEHIND": 7,
            "SMOKING": 7,
        }
    )

    AgentRuntimeService._apply_response_personalization(
        profile=profile,
        behavior_type="PHONE_USE",
        response_type=DriverResponseType.VOICE_ACCEPTED,
        behavior_corrected=True,
    )

    assert profile.behavior_warning_sensitivity["PHONE_USE"] == 8


def test_response_personalization_clamps_to_supported_range() -> None:
    profile = SimpleNamespace(
        behavior_warning_sensitivity={
            "DROWSINESS": 9,
            "PHONE_USE": 10,
            "FOOD_OR_DRINK": 7,
            "GAZE_AWAY": 9,
            "SECONDARY_TASK": 7,
            "REACHING_BEHIND": 7,
            "SMOKING": 7,
        }
    )

    AgentRuntimeService._apply_response_personalization(
        profile=profile,
        behavior_type="PHONE_USE",
        response_type=DriverResponseType.NO_RESPONSE,
        behavior_corrected=False,
    )

    assert profile.behavior_warning_sensitivity["PHONE_USE"] == 10
