from copy import deepcopy
from queue import Queue
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from internal.entity.app_entity import DEFAULT_APP_CONFIG
from test.integration.conftest import assert_success
from test.integration.handler.test_database_http_routes import APP_PAYLOAD


pytestmark = pytest.mark.integration


@pytest.fixture()
def app_record(client, db_session):
    from internal.model import App

    created = assert_success(client.post("/apps", json=APP_PAYLOAD))
    return db_session.get(App, UUID(created["data"]["id"]))


def test_app_config_publish_history_and_fallback_routes(
    client, db_session, app_record
):
    from internal.model import App, AppConfigVersion

    draft = assert_success(client.get(f"/apps/{app_record.id}/draft-app-config"))
    assert "model_config" in draft["data"]

    config = deepcopy(DEFAULT_APP_CONFIG)
    config["preset_prompt"] = "integration prompt"
    config["long_term_memory"] = {"enable": True}
    assert_success(
        client.post(f"/apps/{app_record.id}/draft-app-config", json=config)
    )
    db_session.expire_all()
    assert db_session.get(App, app_record.id).draft_app_config.preset_prompt == "integration prompt"

    assert_success(client.post(f"/apps/{app_record.id}/publish"))
    db_session.expire_all()
    assert db_session.get(App, app_record.id).status == "published"

    histories = assert_success(client.get(f"/apps/{app_record.id}/publish-histories"))
    assert histories["data"]["list"]
    history_id = histories["data"]["list"][0]["id"]

    config["preset_prompt"] = "changed prompt"
    assert_success(
        client.post(f"/apps/{app_record.id}/draft-app-config", json=config)
    )
    assert_success(
        client.post(
            f"/apps/{app_record.id}/fallback-history",
            json={"app_config_version_id": history_id},
        )
    )
    db_session.expire_all()
    assert db_session.get(App, app_record.id).draft_app_config.preset_prompt == "integration prompt"

    assert_success(client.post(f"/apps/{app_record.id}/cancel-publish"))
    db_session.expire_all()
    assert db_session.get(App, app_record.id).status == "draft"


def test_app_debug_conversation_routes(client, db_session, app_record):
    from internal.model import App, Conversation

    config = deepcopy(DEFAULT_APP_CONFIG)
    config["long_term_memory"] = {"enable": True}
    assert_success(
        client.post(f"/apps/{app_record.id}/draft-app-config", json=config)
    )

    summary = assert_success(client.get(f"/apps/{app_record.id}/summary"))
    assert summary["data"]["summary"] == ""
    assert_success(
        client.post(f"/apps/{app_record.id}/summary", json={"summary": "remember"})
    )
    db_session.expire_all()
    app = db_session.get(App, app_record.id)
    conversation_id = app.debug_conversation_id
    assert db_session.get(Conversation, conversation_id).summary == "remember"

    messages = assert_success(
        client.get(f"/apps/{app_record.id}/conversations/messages")
    )
    assert messages["data"]["list"] == []

    assert_success(
        client.post(
            f"/apps/{app_record.id}/conversations/delete-debug-conversation"
        )
    )
    db_session.expire_all()
    assert db_session.get(App, app_record.id).debug_conversation_id is None


class SynchronousThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


class EmptyGraph:
    def add_node(self, *args, **kwargs):
        pass

    def set_entry_point(self, *args, **kwargs):
        pass

    def add_conditional_edges(self, *args, **kwargs):
        pass

    def add_edge(self, *args, **kwargs):
        pass

    def compile(self):
        return self

    def invoke(self, *args, **kwargs):
        return None


def test_app_debug_stream_stop_and_ping_routes(
    client, app_record, handler_for, monkeypatch
):
    import internal.handler.app_handler as app_handler_module

    monkeypatch.setattr(app_handler_module, "Thread", SynchronousThread)
    monkeypatch.setattr(app_handler_module, "StateGraph", lambda *args: EmptyGraph())
    app_handler = handler_for("debug")
    fake_tool = lambda: MagicMock()
    app_handler.builtin_provider_manager = MagicMock()
    app_handler.builtin_provider_manager.get_tool.return_value = fake_tool
    fake_llm = MagicMock(features=[], metadata={})
    fake_llm.invoke.return_value.content = "ok"
    app_handler.language_model_manager = MagicMock()
    app_handler.language_model_manager.create_system_chat_model.return_value = fake_llm

    debug_response = client.post(
        f"/apps/{app_record.id}/debug", json={"query": "hello"}
    )
    assert debug_response.status_code == 200
    assert debug_response.mimetype == "text/event-stream"

    app_handler.app_service.debug_chat = MagicMock(
        return_value=iter(["event: done\ndata: {}\n\n"])
    )
    chat_response = client.post(
        f"/apps/{app_record.id}/conversations", json={"query": "hello"}
    )
    assert chat_response.mimetype == "text/event-stream"
    assert b"event: done" in chat_response.get_data()

    app_handler.app_service.stop_debug_chat = MagicMock()
    assert_success(
        client.post(
            f"/apps/{app_record.id}/conversations/tasks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/stop"
        )
    )
    app_handler.app_service.stop_debug_chat.assert_called_once()
    assert_success(client.get("/ping"))
