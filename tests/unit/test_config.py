import pytest
from pydantic import ValidationError

from app.core.config import Settings, parse_cors_origins


def test_parse_cors_origins_from_comma_separated_string() -> None:
    assert parse_cors_origins("http://localhost:5173, https://example.com") == [
        "http://localhost:5173",
        "https://example.com",
    ]


def test_parse_cors_origins_from_json_array_string() -> None:
    assert parse_cors_origins('["http://localhost:5173", "https://example.com"]') == [
        "http://localhost:5173",
        "https://example.com",
    ]


def test_settings_exposes_parsed_cors_origins() -> None:
    settings = Settings(cors_origins="http://localhost:5173,https://example.com")

    assert settings.cors_origin_list == ["http://localhost:5173", "https://example.com"]


def test_settings_validates_default_admin_account_id() -> None:
    settings = Settings(
        default_admin_account_id="00000000-0000-0000-0000-000000000001",
    )

    assert settings.default_admin_account_id == "00000000-0000-0000-0000-000000000001"


def test_settings_rejects_invalid_default_admin_account_id() -> None:
    with pytest.raises(ValidationError):
        Settings(default_admin_account_id="not-a-uuid")


def test_settings_normalizes_empty_default_admin_email_to_none() -> None:
    settings = Settings(default_admin_email=" ")

    assert settings.default_admin_email is None
