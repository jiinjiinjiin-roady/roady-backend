from datetime import UTC, datetime


def utc_now_for_api_response() -> datetime:
    return datetime.now(UTC)


def utc_now_for_mysql_datetime() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_utc_datetime(value: datetime) -> str:
    utc_value = ensure_utc_datetime(value)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
