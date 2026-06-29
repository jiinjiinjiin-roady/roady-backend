import pytest

from app.core.config import Settings
from app.db.seed import SeedError, run_seed, seed_default_admin_account
from app.models import Account


class FakeScalarResult:
    def __init__(self, account: Account | None) -> None:
        self.account = account

    def scalar_one_or_none(self) -> Account | None:
        return self.account


class FakeSession:
    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.conflicting_account: Account | None = None
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, model: type[Account], key: str) -> Account | None:
        assert model is Account
        return self.accounts.get(key)

    async def execute(self, statement: object) -> FakeScalarResult:
        assert statement is not None
        return FakeScalarResult(self.conflicting_account)

    def add(self, account: Account) -> None:
        self.accounts[account.id] = account

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def make_settings(**overrides: object) -> Settings:
    values = {
        "mysql_password": "test-password",
        "default_admin_account_id": "00000000-0000-0000-0000-000000000001",
        "default_admin_email": "admin@example.com",
    }
    values.update(overrides)
    return Settings(**values)


async def test_seed_creates_default_admin_account() -> None:
    session = FakeSession()

    result = await seed_default_admin_account(session, make_settings())

    assert result == "created"
    account = session.accounts["00000000-0000-0000-0000-000000000001"]
    assert account.email == "admin@example.com"


async def test_seed_is_idempotent_for_existing_matching_account() -> None:
    session = FakeSession()
    session.accounts["00000000-0000-0000-0000-000000000001"] = Account(
        id="00000000-0000-0000-0000-000000000001",
        email="admin@example.com",
    )

    result = await seed_default_admin_account(session, make_settings())

    assert result == "unchanged"
    assert len(session.accounts) == 1


async def test_seed_updates_email_for_existing_admin_id() -> None:
    session = FakeSession()
    session.accounts["00000000-0000-0000-0000-000000000001"] = Account(
        id="00000000-0000-0000-0000-000000000001",
        email="old@example.com",
    )

    result = await seed_default_admin_account(
        session,
        make_settings(default_admin_email="new@example.com"),
    )

    assert result == "updated"
    assert session.accounts["00000000-0000-0000-0000-000000000001"].email == "new@example.com"


async def test_seed_fails_when_email_belongs_to_another_account() -> None:
    session = FakeSession()
    session.conflicting_account = Account(
        id="00000000-0000-0000-0000-000000000099",
        email="admin@example.com",
    )

    with pytest.raises(SeedError):
        await seed_default_admin_account(session, make_settings())

    assert "00000000-0000-0000-0000-000000000001" not in session.accounts


async def test_run_seed_commits_on_success() -> None:
    session = FakeSession()

    result = await run_seed(make_settings(), session_factory=lambda: session)

    assert result == "created"
    assert session.committed is True
    assert session.rolled_back is False


async def test_run_seed_rolls_back_on_failure() -> None:
    session = FakeSession()
    session.conflicting_account = Account(
        id="00000000-0000-0000-0000-000000000099",
        email="admin@example.com",
    )

    with pytest.raises(SeedError):
        await run_seed(make_settings(), session_factory=lambda: session)

    assert session.committed is False
    assert session.rolled_back is True
