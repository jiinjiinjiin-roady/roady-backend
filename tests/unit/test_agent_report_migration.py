import importlib.util
from pathlib import Path
from types import ModuleType


def load_fourth_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0004_create_agent_and_report_tables.py"
    )
    spec = importlib.util.spec_from_file_location(
        "revision_0004_create_agent_and_report_tables",
        revision_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fourth_revision_metadata() -> None:
    revision = load_fourth_revision()

    assert revision.revision == "0004_agent_report_tables"
    assert revision.down_revision == "0003_driving_safety_tables"


def test_fourth_revision_contains_explicit_agent_and_report_schema() -> None:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0004_create_agent_and_report_tables.py"
    )
    source = revision_path.read_text(encoding="utf-8")

    assert '"agent_conversations"' in source
    assert '"agent_messages"' in source
    assert '"tool_executions"' in source
    assert '"report_exports"' in source
    assert "mysql.INTEGER(unsigned=True)" in source
    assert "mysql.DATETIME(fsp=6)" in source
    assert "mysql.JSON()" in source
    assert "sa.Boolean()" in source
    assert "sa.Date()" in source
    assert "uq_agent_messages_conversation_sequence" in source
    assert "ck_tool_executions_confirmation_required_status" in source
    assert "ck_report_exports_email_requires_recipient" in source
    assert "ondelete=\"CASCADE\"" in source
    assert "ondelete=\"SET NULL\"" in source
    assert "onupdate=\"RESTRICT\"" in source
    assert "idx_agent_conversations_session_time" in source
    assert "idx_agent_messages_conversation_time" in source
    assert "idx_report_exports_profile_created_at" in source
    assert "op.drop_table(\"report_exports\")" in source
    assert "op.drop_table(\"tool_executions\")" in source
    assert "op.drop_table(\"agent_messages\")" in source
    assert "op.drop_table(\"agent_conversations\")" in source
    assert "report_session_links" not in source
    assert "report_export_sessions" not in source
    assert "driving_session_report_exports" not in source
