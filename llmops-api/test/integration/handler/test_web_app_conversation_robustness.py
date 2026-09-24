import json
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent
from internal.model import App, Conversation, Message, MessageAgentThought
from test.integration.conftest import assert_success
from test.integration.handler.test_database_http_routes import APP_PAYLOAD

pytestmark = pytest.mark.integration


def _published_app(client, db_session):
    app_id = UUID(assert_success(client.post("/apps", json=APP_PAYLOAD))["data"]["id"])
    assert_success(client.post(f"/apps/{app_id}/publish"))
    assert_success(client.get(f"/apps/{app_id}/published-config"))
    app = db_session.get(App, app_id)
    return app, app.token


def test_web_app_chat_persists_its_own_conversation_and_reuses_it(client, db_session, account, handler_for, monkeypatch):
    from internal.service import web_app_service as module

    app, token = _published_app(client, db_session)
    service = handler_for("web_app_chat").web_app_service
    monkeypatch.setattr(type(service.language_model_manager), "create_language_model", lambda self, _: object())
    monkeypatch.setattr(service.app_config_service, "get_langchain_tools_by_tools_config", lambda _: [])

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def stream(self, _):
            task_id = uuid4()
            yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.AGENT_MESSAGE, answer="answer")
            yield AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.AGENT_END)

    class InlineThread:
        def __init__(self, target, kwargs=None):
            self.target, self.kwargs = target, kwargs or {}

        def start(self):
            self.target(**self.kwargs)

    monkeypatch.setattr(module, "FunctionCallAgent", FakeAgent)
    monkeypatch.setattr(module, "Thread", InlineThread)

    first = client.post(f"/web-apps/{token}/chat", json={"query": "hello"})
    assert first.mimetype == "text/event-stream"
    frames = first.get_data(as_text=True)
    payload = json.loads(next(line[6:] for line in frames.splitlines() if line.startswith("data: ")))
    conversation_id = UUID(payload["conversation_id"])
    message_id = UUID(payload["message_id"])
    saved = db_session.get(Conversation, conversation_id)
    assert saved.app_id == app.id and saved.created_by == account.id
    assert saved.invoke_from == "web_app" and not saved.is_deleted
    assert db_session.get(Message, message_id).answer == "answer"
    assert db_session.query(MessageAgentThought).filter_by(message_id=message_id).count() == 1

    second = client.post(f"/web-apps/{token}/chat", json={"query": "again", "conversation_id": str(conversation_id)})
    second_payload = json.loads(next(line[6:] for line in second.get_data(as_text=True).splitlines() if line.startswith("data: ")))
    assert second_payload["conversation_id"] == str(conversation_id)
    assert db_session.query(Conversation).filter_by(app_id=app.id, created_by=account.id, invoke_from="web_app").count() == 1

    disconnected = client.post(
        f"/web-apps/{token}/chat",
        json={"query": "disconnect", "conversation_id": str(conversation_id)},
        buffered=False,
    )
    for chunk in disconnected.response:
        if b"event: agent_message" in chunk:
            break
    disconnected.close()
    db_session.expire_all()
    assert db_session.query(Message).filter_by(conversation_id=conversation_id, answer="answer").count() == 3


def test_web_app_listing_stop_and_conversation_routes_enforce_owner_and_soft_delete(client, db_session, account, other_account, handler_for, monkeypatch):
    app, token = _published_app(client, db_session)
    own = Conversation(id=uuid4(), app_id=app.id, created_by=account.id, invoke_from="web_app", name="Own")
    foreign = Conversation(id=uuid4(), app_id=app.id, created_by=other_account.id, invoke_from="web_app", name="Private")
    pinned = Conversation(id=uuid4(), app_id=app.id, created_by=account.id, invoke_from="web_app", name="Pinned", is_pinned=True)
    db_session.add_all([own, foreign, pinned])
    db_session.flush()
    message = Message(id=uuid4(), app_id=app.id, conversation_id=own.id, created_by=account.id,
                      invoke_from="web_app", query="Q", answer="A", status="normal")
    mismatched = Message(id=uuid4(), app_id=uuid4(), conversation_id=own.id, created_by=account.id,
                         invoke_from="service_api", query="Private", answer="Private", status="normal")
    db_session.add_all([message, mismatched])
    db_session.flush()

    listed = assert_success(client.get(f"/web-apps/{token}/conversations"))["data"]
    assert {item["id"] for item in listed} == {str(own.id)}
    pinned_list = assert_success(client.get(f"/web-apps/{token}/conversations?is_pinned=true"))["data"]
    assert {item["id"] for item in pinned_list} == {str(pinned.id)}
    for method, path in [
        ("get", f"/conversations/{foreign.id}/name"),
        ("post", f"/conversations/{foreign.id}/name"),
        ("get", f"/conversations/{foreign.id}/messages"),
        ("post", f"/conversations/{foreign.id}/delete"),
        ("post", f"/conversations/{foreign.id}/is-pinned"),
    ]:
        response = getattr(client, method)(path, json={"name": "changed", "is_pinned": True} if method == "post" else None)
        assert response.get_json()["code"] == "not_found"
    assert db_session.get(Conversation, foreign.id).name == "Private"

    assert assert_success(client.get(f"/conversations/{own.id}/name"))["data"]["name"] == "Own"
    assert_success(client.post(f"/conversations/{own.id}/name", json={"name": "Renamed"}))
    assert_success(client.post(f"/conversations/{own.id}/is-pinned", json={"is_pinned": True}))
    assert db_session.get(Conversation, own.id).name == "Renamed"
    assert db_session.get(Conversation, own.id).is_pinned is True
    messages = assert_success(client.get(f"/conversations/{own.id}/messages", query_string={"created_at": int(datetime.now().timestamp()) + 10}))["data"]
    assert [item["id"] for item in messages["list"]] == [str(message.id)]
    assert client.get(f"/conversations/{own.id}/messages", query_string={"created_at": "999999999999999999999"}).get_json()["code"] == "validate_error"
    assert client.post(f"/conversations/{pinned.id}/messages/{message.id}/delete").get_json()["code"] == "not_found"
    assert client.post(f"/conversations/{own.id}/messages/{mismatched.id}/delete").get_json()["code"] == "not_found"
    assert db_session.get(Message, mismatched.id).is_deleted is False
    assert_success(client.post(f"/conversations/{own.id}/messages/{message.id}/delete"))
    assert db_session.get(Message, message.id).is_deleted is True
    assert assert_success(client.get(f"/conversations/{own.id}/messages"))["data"]["list"] == []
    assert_success(client.post(f"/conversations/{own.id}/delete"))
    assert db_session.get(Conversation, own.id).is_deleted is True
    assert client.get(f"/conversations/{own.id}/name").get_json()["code"] == "not_found"

    stop_calls = []
    monkeypatch.setattr("internal.service.web_app_service.AgentQueueManager.set_stop_flag", lambda *args: stop_calls.append(args))
    task_id = uuid4()
    assert_success(client.post(f"/web-apps/{token}/chat/{task_id}/stop"))
    assert stop_calls == [(task_id, "web_app", account.id)]


def test_web_app_chat_rejects_foreign_or_deleted_conversation(client, db_session, account, other_account):
    app, token = _published_app(client, db_session)
    records = [
        Conversation(id=uuid4(), app_id=app.id, created_by=other_account.id, invoke_from="web_app"),
        Conversation(id=uuid4(), app_id=app.id, created_by=account.id, invoke_from="web_app", is_deleted=True),
    ]
    db_session.add_all(records)
    db_session.flush()
    for record in records:
        result = client.post(f"/web-apps/{token}/chat", json={"query": "hello", "conversation_id": str(record.id)})
        assert result.get_json()["code"] == "forbidden"
    invalid = client.post(f"/web-apps/{token}/chat", json={"query": "hello", "conversation_id": "not-a-uuid"})
    assert invalid.get_json()["code"] == "validate_error"
    assert db_session.query(Message).filter_by(app_id=app.id).count() == 0


def test_web_app_model_setup_failure_does_not_create_empty_message(client, db_session, handler_for, monkeypatch):
    app, token = _published_app(client, db_session)
    service = handler_for("web_app_chat").web_app_service

    def fail_model(_self, _config):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(type(service.language_model_manager), "create_language_model", fail_model)
    response = client.post(f"/web-apps/{token}/chat", json={"query": "hello"})

    assert response.get_json()["code"] == "fail"
    assert db_session.query(Message).filter_by(app_id=app.id).count() == 0
    assert db_session.query(Conversation).filter_by(app_id=app.id, invoke_from="web_app").count() == 0
