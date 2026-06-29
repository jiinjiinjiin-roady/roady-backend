import importlib.util
from pathlib import Path
from types import ModuleType


def load_first_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_create_accounts.py"
    )
    spec = importlib.util.spec_from_file_location("revision_0001_create_accounts", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_first_revision_metadata() -> None:
    revision = load_first_revision()

    assert revision.revision == "0001_create_accounts"
    assert revision.down_revision is None


def test_first_revision_contains_explicit_accounts_schema() -> None:
    revision_path = (
        Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_create_accounts.py"
    )
    source = revision_path.read_text(encoding="utf-8")

    assert "op.create_table(" in source
    assert '"accounts"' in source
    assert 'sa.CHAR(length=36)' in source
    assert 'sa.String(length=320)' in source
    assert 'mysql.DATETIME(fsp=6)' in source
    assert 'CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)' in source
    assert 'sa.UniqueConstraint("email", name="uq_accounts_email")' in source
    assert 'mysql_charset="utf8mb4"' in source
    assert 'mysql_collate="utf8mb4_0900_ai_ci"' in source
    assert "op.drop_table(\"accounts\")" in source
