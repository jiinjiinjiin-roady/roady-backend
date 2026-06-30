from uuid import UUID, uuid4


def generate_uuid4() -> str:
    return str(uuid4())


def normalize_uuid_string(value: str) -> str:
    return str(UUID(str(value)))
