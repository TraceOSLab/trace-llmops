import os
from datetime import datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import scoped_session, sessionmaker


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires the isolated PostgreSQL test database")


def _validated_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL", "")
    if not database_url:
        pytest.exit(
            "集成测试需要 TEST_DATABASE_URL；请在仓库根目录执行 ./scripts/test.sh。",
            returncode=2,
        )
    url = make_url(database_url)
    if "test" not in (url.database or "").lower():
        pytest.exit("安全检查失败：数据库名必须包含 test。", returncode=2)
    if url.host not in {"127.0.0.1", "localhost"} or url.port != 55432:
        pytest.exit(
            "安全检查失败：集成测试只允许连接 127.0.0.1:55432。",
            returncode=2,
        )
    return database_url


@pytest.fixture(scope="session")
def app():
    database_url = _validated_database_url()
    os.environ["SQLALCHEMY_DATABASE_URI"] = database_url
    os.environ.setdefault(
        "JWT_SECRET_KEY", "integration-test-secret-key-32-bytes"
    )
    os.environ["WTF_CSRF_ENABLED"] = "False"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"

    from app.http.app import create_app

    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    from internal.extension.database_extension import db

    with flask_app.app_context():
        revision = db.session.execute(text("select version_num from alembic_version")).scalar_one_or_none()
        if revision is None:
            pytest.exit("测试数据库尚未执行迁移，请使用 ./scripts/test.sh。", returncode=2)
    return flask_app


@pytest.fixture(scope="session", autouse=True)
def require_all_routes_to_be_exercised(app):
    from flask import request

    expected = {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    visited = set()

    @app.before_request
    def _record_endpoint():
        if request.endpoint:
            visited.add(request.endpoint)

    yield
    missing = sorted(expected - visited)
    assert len(expected) == 85
    assert not missing, f"以下 Handler 路由未被 HTTP 集成测试执行: {missing}"


@pytest.fixture()
def db_session(app):
    from internal.extension.database_extension import db

    with app.app_context():
        connection = db.engine.connect()
        outer_transaction = connection.begin()
        original_session = db.session
        test_session = scoped_session(
            sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
        )
        db.session = test_session
        try:
            yield test_session
        finally:
            test_session.remove()
            db.session = original_session
            outer_transaction.rollback()
            connection.close()


@pytest.fixture()
def account(db_session):
    from internal.model import Account

    record = Account(
        id=uuid4(),
        name="integration-user",
        email=f"{uuid4().hex}@example.com",
        avatar="",
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture()
def other_account(db_session):
    from internal.model import Account

    record = Account(
        id=uuid4(),
        name="other-user",
        email=f"{uuid4().hex}@example.com",
        avatar="",
    )
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture()
def auth_headers(account):
    expires_at = datetime.now() + timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(account.id), "iss": "llmops", "exp": expires_at},
        os.environ["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(app, db_session, auth_headers):
    test_client = app.test_client()
    test_client.environ_base["HTTP_AUTHORIZATION"] = auth_headers["Authorization"]
    return test_client


@pytest.fixture()
def anonymous_client(app, db_session):
    return app.test_client()


@pytest.fixture()
def handler_for(app):
    def _handler(method_name: str, blueprint: str = "llmops"):
        return app.view_functions[f"{blueprint}.{method_name}"].__self__

    return _handler


@pytest.fixture(autouse=True)
def forbid_public_http(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("集成测试禁止访问公网")

    monkeypatch.setattr("requests.sessions.Session.request", _blocked)


def assert_success(response):
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "success"
    return payload
