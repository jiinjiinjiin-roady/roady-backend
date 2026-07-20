import pytest

from app.policies.agent_demo_policy import (
    AgentReplyPlan,
    ToolPlan,
    plan_agent_reply,
    validate_agent_reply_plan,
    validate_safety_guidance_text,
)


def test_rule_based_reply_for_message_requires_confirmation() -> None:
    plan = validate_agent_reply_plan(plan_agent_reply(text="아빠한테 문자 보내줘"))

    assert plan.intent == "SEND_MESSAGE"
    assert plan.tool is not None
    assert plan.tool.tool_name == "message.prepare"
    assert plan.tool.confirmation_required is True
    assert plan.tool.result is None


def test_reply_validation_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match="tool is not allowed"):
        validate_agent_reply_plan(
            AgentReplyPlan(
                intent="PLAY_MUSIC",
                text="요청을 처리할게요.",
                tool=ToolPlan(
                    tool_name="unsafe.execute",
                    arguments={},
                    result=None,
                    confirmation_required=False,
                    intent="PLAY_MUSIC",
                ),
            )
        )


def test_reply_validation_rejects_message_tool_without_confirmation() -> None:
    with pytest.raises(ValueError, match="requires confirmation"):
        validate_agent_reply_plan(
            AgentReplyPlan(
                intent="SEND_MESSAGE",
                text="메시지를 바로 보낼게요.",
                tool=ToolPlan(
                    tool_name="message.prepare",
                    arguments={},
                    result=None,
                    confirmation_required=False,
                    intent="SEND_MESSAGE",
                ),
            )
        )


def test_safety_guidance_validation_normalizes_text() -> None:
    speech_text, ui_text = validate_safety_guidance_text(
        speech_text="  전방을 다시 확인해 주세요.  ",
        ui_text="  전방 주시 이탈  ",
    )

    assert speech_text == "전방을 다시 확인해 주세요."
    assert ui_text == "전방 주시 이탈"
