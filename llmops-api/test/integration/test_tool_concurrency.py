from concurrent.futures import ThreadPoolExecutor
from copy import copy
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.orm import scoped_session, sessionmaker

from internal.exception import ValidateErrorException
from internal.model import Account, ApiTool, ApiToolProvider
from pkg.sqlalchemy import SQLAlchemy
from test.integration.handler.test_database_http_routes import OPENAPI_SCHEMA

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("same_name", [True, False])
def test_concurrent_provider_creation_serializes_name_check(app, handler_for, same_name):
    from internal.extension.database_extension import db
    with app.app_context():
        engine = db.engine
    class TestDB:
        session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
        auto_commit = SQLAlchemy.auto_commit
    database = TestDB()
    owner_id = uuid4()
    with database.auto_commit():
        database.session.add(Account(id=owner_id, email=f"{owner_id}@test.invalid", name="test"))
    database.session.remove()
    first_locked, release, second_started = Event(), Event(), Event()
    second_pid = []

    def run(first):
        service = copy(handler_for("create_api_tool_provider").api_tool_service)
        service.db = database
        original = service._add_tools
        def add_tools(*args):
            if first:
                first_locked.set()
                assert release.wait(10)
            original(*args)
        service._add_tools = add_tools
        name = "first" if first or same_name else "second"
        req = SimpleNamespace(**{key: SimpleNamespace(data=value) for key, value in {
            "name": name, "icon": "https://example.com/icon.png", "headers": [],
            "openapi_schema": OPENAPI_SCHEMA}.items()})
        try:
            if not first:
                second_pid.append(database.session.scalar(text("SELECT pg_backend_pid()")))
                second_started.set()
            service.create_api_tool_provider(req, SimpleNamespace(id=owner_id))
            return "success"
        except ValidateErrorException:
            return "duplicate"
        finally:
            database.session.remove()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, True)
            try:
                assert first_locked.wait(10)
                second = pool.submit(run, False)
                assert second_started.wait(5)
                deadline, waiting = monotonic() + 3, False
                while monotonic() < deadline and not second.done():
                    with engine.connect() as connection:
                        waiting = connection.scalar(text(
                            "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"),
                            {"pid": second_pid[0]})
                    if waiting:
                        break
                    sleep(0.01)
                assert waiting
            finally:
                release.set()
            assert first.result(timeout=5) == "success"
            assert second.result(timeout=5) == ("duplicate" if same_name else "success")
        count = 1 if same_name else 2
        assert database.session.query(ApiToolProvider).filter_by(account_id=owner_id).count() == count
        assert database.session.query(ApiTool).filter_by(account_id=owner_id).count() == count
    finally:
        database.session.remove()
        with engine.begin() as connection:
            for model in (ApiTool, ApiToolProvider):
                connection.execute(delete(model).where(model.account_id == owner_id))
            connection.execute(delete(Account).where(Account.id == owner_id))
