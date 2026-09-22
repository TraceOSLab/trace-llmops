import os
import re
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy.exc import IntegrityError

from internal.model import Account, ApiKey, App, Dataset, Document, Segment, Workflow, ApiToolProvider
from test.integration.conftest import assert_success
from test.integration.handler.test_database_http_routes import APP_PAYLOAD, DATASET_PAYLOAD, WORKFLOW_PAYLOAD, OPENAPI_SCHEMA

pytestmark = pytest.mark.integration


def test_all_private_routes_reject_anonymous_before_business_work(app, anonymous_client):
    public = {"llmops.password_login", "llmops.provider", "llmops.authorize", "llmops.get_language_model_icon"}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.endpoint in public:
            continue
        path = re.sub(r"<uuid:[^>]+>", str(uuid4()), rule.rule)
        path = re.sub(r"<[^>]+>", "test", path)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            response = anonymous_client.open(path, method=method, json={})
            assert response.status_code == 200, (method, path)
            assert response.get_json()["code"] == "unauthorized", (method, path, response.get_json())


@pytest.mark.parametrize("kind", ["expired", "missing_exp", "bad_subject", "deleted_account", "wrong_issuer", "wrong_signature"])
def test_invalid_jwt_is_rejected_by_http(anonymous_client, account, kind):
    payload = {"sub": str(account.id), "iss": "llmops", "exp": 4102444800}
    key = os.environ["JWT_SECRET_KEY"]
    if kind == "expired": payload["exp"] = 1
    if kind == "missing_exp": payload.pop("exp")
    if kind == "bad_subject": payload["sub"] = "bad"
    if kind == "deleted_account": payload["sub"] = str(uuid4())
    if kind == "wrong_issuer": payload["iss"] = "other"
    if kind == "wrong_signature": key = "wrong-secret-key-for-test-at-least-32"
    token = jwt.encode(payload, key, algorithm="HS256")
    response = anonymous_client.get("/account", headers={"Authorization": f"Bearer {token}"})
    assert response.get_json()["code"] == "unauthorized"


@pytest.mark.parametrize("kind", ["disabled", "missing", "orphan"])
def test_openapi_rejects_unusable_keys_before_model(anonymous_client, account, db_session, kind):
    credential = "llmops-v1/security-test"
    if kind != "missing":
        db_session.add(ApiKey(id=uuid4(), account_id=uuid4() if kind == "orphan" else account.id,
                              api_key=credential, is_active=kind != "disabled"))
        db_session.flush()
    response = anonymous_client.post("/openapi/chat", json={}, headers={"Authorization": f"Bearer {credential}"})
    assert response.get_json()["code"] == "unauthorized"


@pytest.mark.parametrize("resource", ["apps", "datasets", "workflows", "api-tools", "openapi/api-keys"])
def test_other_account_cannot_read_update_or_delete_resource(client, other_account, db_session, resource):
    models = {"apps": App, "datasets": Dataset, "workflows": Workflow,
              "api-tools": ApiToolProvider, "openapi/api-keys": ApiKey}
    record = models[resource](id=uuid4(), account_id=other_account.id)
    if resource == "openapi/api-keys": record.api_key = "llmops-v1/other-account"
    db_session.add(record)
    db_session.flush()
    rid = record.id
    listing = assert_success(client.get(f"/{resource}"))
    assert all(item["id"] != str(rid) for item in listing["data"]["list"])
    if resource != "openapi/api-keys":
        result = client.get(f"/{resource}/{rid}").get_json()
        assert result["code"] in {"forbidden", "not_found"}
    response = client.post(f"/{resource}/{rid}/delete")
    assert response.get_json()["code"] in {"forbidden", "not_found"}
    db_session.expire_all()
    assert db_session.get(models[resource], rid) is not None
    payloads = {"apps": APP_PAYLOAD, "datasets": DATASET_PAYLOAD, "workflows": WORKFLOW_PAYLOAD,
                "api-tools": {"name": "updated-tools", "icon": "https://example.com/tool.png",
                              "openapi_schema": OPENAPI_SCHEMA, "headers": []},
                "openapi/api-keys": {"is_active": False, "remark": "unauthorized-change"}}
    result = client.post(f"/{resource}/{rid}", json=payloads[resource]).get_json()
    assert result["code"] in {"forbidden", "not_found"}, result
    db_session.expire_all()
    unchanged = db_session.get(models[resource], rid)
    assert unchanged.account_id == other_account.id
    if resource == "openapi/api-keys":
        assert unchanged.remark != "unauthorized-change"
    else:
        assert unchanged.name == ""


def test_nested_documents_and_segments_reject_wrong_parent_and_owner(client, account, other_account, db_session):
    dataset = Dataset(id=uuid4(), account_id=account.id)
    foreign = Dataset(id=uuid4(), account_id=other_account.id)
    document = Document(id=uuid4(), account_id=other_account.id, dataset_id=foreign.id,
                        upload_file_id=uuid4(), process_rule_id=uuid4())
    segment = Segment(id=uuid4(), account_id=other_account.id, dataset_id=foreign.id,
                      document_id=document.id, node_id=uuid4())
    db_session.add_all([dataset, foreign, document, segment])
    db_session.flush()
    for parent in (dataset.id, foreign.id):
        base = f"/datasets/{parent}/documents/{document.id}"
        for path in (base, f"{base}/segments", f"{base}/segments/{segment.id}"):
            assert client.get(path).get_json()["code"] in {"forbidden", "not_found"}
        response = client.post(f"{base}/name", json={"name": "unauthorized-change"})
        assert response.get_json()["code"] in {"forbidden", "not_found"}
    db_session.expire_all()
    assert db_session.get(Document, document.id).name != "unauthorized-change"


@pytest.mark.parametrize("query", [{"page_size": ""}, {"page_size": "0"}, {"current_page": "abc"}, {"page_size": "51"}])
def test_pagination_validation_reaches_all_relevant_handlers(client, query):
    for path in ("/apps", "/datasets", "/openapi/api-keys", "/assistant-agent/messages",
                 f"/apps/{uuid4()}/publish-histories"):
        assert client.get(path, query_string=query).get_json()["code"] == "validate_error", path


def test_assistant_routes_keep_account_context_and_persist_clear(client, account, other_account, db_session, handler_for, monkeypatch):
    service = handler_for("assistant_agent_chat").assistant_agent_service
    chat = MagicMock(return_value=iter(["event: agent_end\ndata: {}\n\n"]))
    identities = []
    stop = MagicMock(side_effect=lambda task, user: identities.append((task, user.id)))
    monkeypatch.setattr(service, "assistant_agent_chat", chat)
    monkeypatch.setattr(service, "stop_assistant_agent_chat", stop)
    response = client.post("/assistant-agent/chat", json={"query": "hello"})
    assert response.mimetype == "text/event-stream"
    assert b"agent_end" in response.get_data()
    chat.assert_called_once_with("hello", account.id)
    task_id = uuid4()
    assert_success(client.post(f"/assistant-agent/chat/{task_id}/stop"))
    assert identities == [(task_id, account.id)]
    page = assert_success(client.get("/assistant-agent/messages", query_string={"page_size": 1}))
    assert page["data"]["paginator"]["page_size"] == 1
    conversation_id = account.assistant_agent_conversation_id
    assert conversation_id is not None
    other_account.assistant_agent_conversation_id = uuid4()
    other_id = other_account.assistant_agent_conversation_id
    db_session.flush()
    assert_success(client.post("/assistant-agent/delete-conversation"))
    db_session.expire_all()
    assert db_session.get(Account, account.id).assistant_agent_conversation_id is None
    assert db_session.get(Account, other_account.id).assistant_agent_conversation_id == other_id


def test_analysis_requires_app_owner_and_uses_real_calculation(client, other_account, db_session, handler_for, monkeypatch):
    created = assert_success(client.post("/apps", json=APP_PAYLOAD))
    app_id = created["data"]["id"]
    cache = MagicMock()
    cache.exists.return_value = False
    monkeypatch.setattr(handler_for("get_app_analysis").analysis_service, "redis_client", cache)
    result = assert_success(client.get(f"/analysis/{app_id}"))["data"]
    assert result["total_messages"]["data"] == 0
    record = db_session.get(App, UUID(app_id))
    record.account_id = other_account.id
    db_session.flush()
    cache.reset_mock()
    assert client.get(f"/analysis/{app_id}").get_json()["code"] == "forbidden"
    cache.exists.assert_not_called()


def test_failed_transaction_can_be_followed_by_valid_database_write(db_session):
    from internal.extension.database_extension import db
    failed_id, good_id = uuid4(), uuid4()
    with pytest.raises(IntegrityError):
        with db.auto_commit():
            db_session.add(Account(id=failed_id, email=None))
            # A raw NULL bypasses the server default to force a real constraint failure.
            from sqlalchemy import null
            db_session.query(Account).filter(Account.id == failed_id).update({Account.email: null()})
    with db.auto_commit():
        db_session.add(Account(id=good_id, email="recovered@example.com"))
    db_session.expire_all()
    assert db_session.get(Account, failed_id) is None
    assert db_session.get(Account, good_id).email == "recovered@example.com"


def test_password_failure_does_not_change_login_state(client, anonymous_client, account, db_session):
    assert_success(client.post("/account/password", json={"password": "abcd1234"}))
    previous = account.last_login_at
    for email, password in [(account.email, "wrong123"), ("unknown@example.com", "abcd1234")]:
        result = anonymous_client.post("/auth/password-login", json={"email": email, "password": password}).get_json()
        assert result["code"] == "fail"
        assert result["message"] == "账号不存在或密码错误，请重试"
    db_session.expire_all()
    assert db_session.get(Account, account.id).last_login_at == previous


def test_deleted_api_key_cannot_authenticate(client, anonymous_client, account, db_session):
    record = ApiKey(id=uuid4(), account_id=account.id, api_key="llmops-v1/deleted", is_active=True)
    db_session.add(record)
    db_session.flush()
    assert_success(client.post(f"/openapi/api-keys/{record.id}/delete"))
    response = anonymous_client.post("/openapi/chat", json={}, headers={"Authorization": "Bearer llmops-v1/deleted"})
    assert response.get_json()["code"] == "unauthorized"


@pytest.mark.parametrize("existing_account", [False, True])
def test_oauth_failure_rolls_back_account_and_link(anonymous_client, db_session, handler_for, monkeypatch, existing_account):
    from pkg.oauth.oauth import OAuthUserInfo
    from internal.model import AccountOAuth
    email = "oauth-rollback@example.com"
    if existing_account:
        db_session.add(Account(id=uuid4(), name="before", email=email))
        db_session.commit()
    service = handler_for("authorize").oauth_service
    provider = MagicMock()
    provider.get_access_token.return_value = "fake-provider-token"
    provider.get_user_info.return_value = OAuthUserInfo("test-subject", "new-name", email)
    monkeypatch.setattr(service, "get_oauth_by_provider_name", lambda name: provider)
    monkeypatch.setattr(service.jwt_service, "generate_token", MagicMock(side_effect=RuntimeError("token signing failed")))
    response = anonymous_client.post("/oauth/authorize/github", json={"code": "test-code"})
    assert response.get_json()["code"] == "fail"
    db_session.expire_all()
    assert db_session.query(AccountOAuth).filter_by(openid="test-subject").count() == 0
    assert db_session.query(Account).filter_by(email=email).count() == int(existing_account)


def test_oauth_login_reuses_account_and_identity(anonymous_client, db_session, handler_for, monkeypatch):
    from pkg.oauth.oauth import OAuthUserInfo
    from internal.model import AccountOAuth
    email = "oauth-success@example.com"
    existing = Account(id=uuid4(), name="existing", email=email)
    db_session.add(existing)
    db_session.flush()
    provider = MagicMock()
    provider.get_access_token.side_effect = ["fake-token-1", "fake-token-2"]
    provider.get_user_info.return_value = OAuthUserInfo("oauth-id", "external", email)
    service = handler_for("authorize").oauth_service
    monkeypatch.setattr(service, "get_oauth_by_provider_name", lambda name: provider)
    for _ in range(2):
        data = assert_success(anonymous_client.post("/oauth/authorize/github", json={"code": "test"}))["data"]
        assert service.jwt_service.parse_token(data["access_token"])["sub"] == str(existing.id)
    db_session.expire_all()
    assert db_session.query(Account).filter_by(email=email).count() == 1
    links = db_session.query(AccountOAuth).filter_by(openid="oauth-id").all()
    assert len(links) == 1 and links[0].encrypted_token == "fake-token-2"
