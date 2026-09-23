from concurrent.futures import ThreadPoolExecutor
from copy import copy, deepcopy
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.orm import scoped_session, sessionmaker

from internal.entity.app_entity import DEFAULT_APP_CONFIG
from internal.model import App, AppConfig, AppConfigVersion, AppDatasetJoin
from pkg.sqlalchemy import SQLAlchemy

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("second_action", ["publish", "update", "cancel"])
def test_lifecycle_writes_are_serialized(app, handler_for, second_action):
    from internal.extension.database_extension import db

    with app.app_context():
        engine = db.engine

    class TestDB:
        session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
        auto_commit = SQLAlchemy.auto_commit

    database = TestDB()
    app_id, draft_id, owner_id = uuid4(), uuid4(), uuid4()
    account = SimpleNamespace(id=owner_id)
    with database.auto_commit():
        database.session.add(App(id=app_id, account_id=owner_id, status="draft", draft_app_config_id=draft_id))
        database.session.add(AppConfigVersion(id=draft_id, app_id=app_id, config_type="draft", version=0,
                                             **deepcopy(DEFAULT_APP_CONFIG)))
    database.session.remove()
    first_locked, release_first, second_started = Event(), Event(), Event()
    second_pid = []

    def run(first):
        service = copy(handler_for("publish_draft_app_config").app_service)
        service.db = database
        original = service._get_draft_record

        def read_draft(record):
            result = original(record)
            if first:
                first_locked.set()
                assert release_first.wait(10)
            return result

        service._get_draft_record = read_draft
        try:
            if not first:
                second_pid.append(database.session.scalar(text("SELECT pg_backend_pid()")))
                second_started.set()
            if first or second_action == "publish":
                service.publish_draft_app_config(app_id, account)
            elif second_action == "update":
                service.update_draft_app_config(app_id, {"preset_prompt": "new draft"}, account)
            else:
                service.cancel_publish_app_config(app_id, account)
        finally:
            database.session.remove()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, True)
            try:
                assert first_locked.wait(10)
                second = pool.submit(run, False)
                assert second_started.wait(5)
                deadline = monotonic() + 3
                waiting = False
                while monotonic() < deadline and not second.done():
                    with engine.connect() as connection:
                        waiting = connection.scalar(text(
                            "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"
                        ), {"pid": second_pid[0]})
                    if waiting:
                        break
                    sleep(0.01)
                assert waiting, "competing app write did not wait for the first transaction"
            finally:
                release_first.set()
            first.result(timeout=5)
            second.result(timeout=5)

        record = database.session.get(App, app_id)
        histories = database.session.query(AppConfigVersion).filter_by(app_id=app_id, config_type="published").all()
        assert sorted(h.version for h in histories) == ([1, 2] if second_action == "publish" else [1])
        if second_action == "cancel":
            assert record.status == "draft" and record.app_config_id is None
        else:
            runtime = database.session.get(AppConfig, record.app_config_id)
            assert record.status == "published" and runtime.preset_prompt == ""
        draft = database.session.get(AppConfigVersion, draft_id)
        assert draft.preset_prompt == ("new draft" if second_action == "update" else "")
    finally:
        database.session.remove()
        with engine.begin() as connection:
            for model in (AppDatasetJoin, AppConfigVersion, AppConfig):
                connection.execute(delete(model).where(model.app_id == app_id))
            connection.execute(delete(App).where(App.id == app_id))
