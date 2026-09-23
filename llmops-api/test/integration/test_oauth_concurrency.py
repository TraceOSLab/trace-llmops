from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import scoped_session, sessionmaker

from internal.model import Account, AccountOAuth
from internal.service.account_service import AccountService
from internal.service.jwt_service import JWTService
from internal.service.oauth_service import OAuthService
from pkg.oauth.oauth import OAuthUserInfo
from pkg.sqlalchemy import SQLAlchemy

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_login_db(app):
    """Real commits and separate connections, not the HTTP fixture's shared savepoint."""
    from internal.extension.database_extension import db

    with app.app_context():
        engine = db.engine

    class LoginDB:
        session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
        auto_commit = SQLAlchemy.auto_commit

    database = LoginDB()
    prefix = f"concurrency-{uuid4().hex}"
    yield database, engine, prefix
    database.session.remove()
    # Only remove this test's committed records from the validated test database.
    with engine.begin() as connection:
        connection.execute(delete(AccountOAuth).where(AccountOAuth.openid.like(f"{prefix}%")))
        connection.execute(delete(Account).where(Account.email.like(f"{prefix}%")))


@pytest.mark.parametrize("scenario", ["same_identity", "shared_email", "changed_email", "unrelated", "rollback"])
def test_concurrent_oauth_login(app, isolated_login_db, scenario):
    database, engine, prefix = isolated_login_db
    first_signed, release_first, second_started = Event(), Event(), Event()
    first_info = OAuthUserInfo(prefix, "first", f"{prefix}@example.com")
    second_info = OAuthUserInfo(
        prefix + ("-second" if scenario in {"shared_email", "unrelated"} else ""),
        "second",
        f"{prefix}{'-second' if scenario in {'changed_email', 'unrelated'} else ''}@example.com",
    )

    def login(first):
        def sign(payload):
            if first:
                first_signed.set()
                assert release_first.wait(10), "test did not release first transaction"
                if scenario == "rollback":
                    raise RuntimeError("simulated signing failure")
            return JWTService.generate_token(payload)

        def identity(token):
            if not first:
                second_started.set()
            return first_info if first else second_info

        jwt_service = SimpleNamespace(generate_token=sign)
        account_service = AccountService(db=database, jwt_service=jwt_service)
        service = OAuthService(db=database, jwt_service=jwt_service, account_service=account_service)
        service.get_oauth_by_provider_name = lambda name: SimpleNamespace(
            get_access_token=lambda code: "fake-token", get_user_info=identity,
        )
        try:
            with app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                return service.oauth_login("github", "fake-code")
        finally:
            database.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(login, True)
        try:
            assert first_signed.wait(10)
            second = pool.submit(login, False)
            assert second_started.wait(5)
            # Wait for a real PostgreSQL advisory-lock waiter, or for the unfixed
            # competing login to finish. Avoid a barrier inside the locked section.
            deadline = monotonic() + 3
            waiting = False
            while not second.done() and monotonic() < deadline:
                with engine.connect() as connection:
                    waiting = bool(connection.scalar(text(
                        "SELECT EXISTS (SELECT 1 FROM pg_locks "
                        "WHERE locktype = 'advisory' AND NOT granted "
                        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()))"
                    )))
                if waiting:
                    break
                sleep(0.01)
            if scenario == "unrelated":
                assert second.done(), "unrelated identities must not block each other"
            else:
                assert waiting or second.done(), "second transaction did not make progress"
        finally:
            release_first.set()
        if scenario == "rollback":
            with pytest.raises(RuntimeError, match="simulated signing failure"):
                first.result(timeout=5)
        else:
            first_result = first.result(timeout=5)
        second_result = second.result(timeout=5)

    with database.auto_commit():
        accounts = database.session.scalars(select(Account).where(Account.email.like(f"{prefix}%"))).all()
        links = database.session.scalars(select(AccountOAuth).where(AccountOAuth.openid.like(f"{prefix}%"))).all()
        assert len(accounts) == (2 if scenario == "unrelated" else 1)
        assert len(links) == (2 if scenario in {"shared_email", "unrelated"} else 1)
        second_id = JWTService.parse_token(second_result["access_token"])["sub"]
        assert second_id in {str(account.id) for account in accounts}
        if scenario not in {"rollback", "unrelated"}:
            assert JWTService.parse_token(first_result["access_token"])["sub"] == second_id


def test_login_lock_timeout_rolls_back_and_does_not_leak_settings(isolated_login_db, monkeypatch):
    from internal.exception import FailException

    database, engine, prefix = isolated_login_db
    monkeypatch.setattr("internal.service.oauth_service.OAUTH_LOCK_TIMEOUT", "100ms")
    service = OAuthService(db=database, jwt_service=JWTService(), account_service=None)

    def competing_lock():
        try:
            with database.auto_commit():
                service._lock_login_identity("github", prefix, f"{prefix}@example.com")
        finally:
            database.session.remove()

    with database.auto_commit():
        before = database.session.scalar(text("SELECT current_setting('lock_timeout')"))
        service._lock_login_identity("github", prefix, f"{prefix}@example.com")
        assert database.session.scalar(text("SELECT current_setting('lock_timeout')")) == before
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(FailException, match="登录请求繁忙"):
                pool.submit(competing_lock).result(timeout=5)
    database.session.remove()
    # Holder has committed, and the failed request has rolled back: both locks
    # and the SET LOCAL override must be gone even on pooled connections.
    competing_lock()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_setting('lock_timeout')")) == before
