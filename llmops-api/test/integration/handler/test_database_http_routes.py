import base64
import json
import secrets
from uuid import UUID

import pytest

from pkg.password import hash_password
from test.integration.conftest import assert_success


pytestmark = pytest.mark.integration


APP_PAYLOAD = {
    "name": "integration-app",
    "icon": "https://example.com/app.png",
    "description": "integration",
}
DATASET_PAYLOAD = {
    "name": "integration-dataset",
    "icon": "https://example.com/dataset.png",
    "description": "integration",
}
WORKFLOW_PAYLOAD = {
    "name": "integration-workflow",
    "tool_call_name": "integration_workflow",
    "icon": "https://example.com/workflow.png",
    "description": "integration",
}
VALID_WORKFLOW_GRAPH = {
    "nodes": [
        {
            "id": "10000000-0000-0000-0000-000000000001",
            "node_type": "start",
            "title": "Start",
            "inputs": [],
        },
        {
            "id": "10000000-0000-0000-0000-000000000002",
            "node_type": "end",
            "title": "End",
            "outputs": [],
        },
    ],
    "edges": [
        {
            "id": "10000000-0000-0000-0000-000000000003",
            "source": "10000000-0000-0000-0000-000000000001",
            "source_type": "start",
            "target": "10000000-0000-0000-0000-000000000002",
            "target_type": "end",
        }
    ],
}
OPENAPI_SCHEMA = json.dumps(
    {
        "description": "integration tools",
        "server": "https://example.com",
        "paths": {
            "/search": {
                "get": {
                    "description": "search",
                    "operationId": "IntegrationSearch",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "description": "query",
                            "required": True,
                            "type": "str",
                        }
                    ],
                }
            }
        },
    }
)


def test_account_and_auth_routes_use_real_database(
    client, anonymous_client, account, db_session
):
    from internal.model import Account

    payload = assert_success(client.get("/account"))
    assert payload["data"]["email"] == account.email

    assert_success(client.post("/account/name", json={"name": "renamed-user"}))
    db_session.expire_all()
    assert db_session.get(Account, account.id).name == "renamed-user"

    avatar = "https://example.com/avatar.png"
    assert_success(client.post("/account/avatar", json={"avatar": avatar}))
    db_session.expire_all()
    assert db_session.get(Account, account.id).avatar == avatar

    assert_success(client.post("/account/password", json={"password": "abcd1234"}))
    db_session.expire_all()
    stored = db_session.get(Account, account.id)
    assert stored.password and stored.password_salt

    login = assert_success(
        anonymous_client.post(
            "/auth/password-login",
            json={"email": stored.email, "password": "abcd1234"},
        )
    )
    assert login["data"]["access_token"]
    assert_success(client.post("/auth/logout"))


def test_authentication_and_validation_failures(anonymous_client, client):
    unauthorized = anonymous_client.get("/account")
    assert unauthorized.status_code == 200
    assert unauthorized.get_json()["code"] != "success"

    invalid = client.post("/apps", json={"name": ""})
    assert invalid.status_code == 200
    assert invalid.get_json()["code"] != "success"


def test_app_crud_routes_persist_and_query(
    client, account, db_session
):
    from internal.model import App

    created = assert_success(client.post("/apps", json=APP_PAYLOAD))
    app_id = UUID(created["data"]["id"])
    db_session.expire_all()
    record = db_session.get(App, app_id)
    assert record is not None and record.account_id == account.id

    assert_success(client.get(f"/apps/{app_id}"))
    listing = assert_success(client.get("/apps", query_string={"search_word": "integration"}))
    assert any(item["id"] == str(app_id) for item in listing["data"]["list"])

    updated_payload = {**APP_PAYLOAD, "name": "updated-integration-app"}
    assert_success(client.post(f"/apps/{app_id}", json=updated_payload))
    db_session.expire_all()
    assert db_session.get(App, app_id).name == "updated-integration-app"

    copied = assert_success(client.post(f"/apps/{app_id}/copy"))
    copy_id = UUID(copied["data"]["id"])
    assert db_session.get(App, copy_id) is not None

    assert_success(client.post(f"/apps/{copy_id}/delete"))
    db_session.expire_all()
    assert db_session.get(App, copy_id) is None


def test_api_key_crud_routes_persist_and_query(client, account, db_session):
    from internal.model import ApiKey

    assert_success(
        client.post(
            "/openapi/api-keys", json={"is_active": True, "remark": "first"}
        )
    )
    record = (
        db_session.query(ApiKey)
        .filter(ApiKey.account_id == account.id, ApiKey.remark == "first")
        .one()
    )
    api_key_id = record.id

    listing = assert_success(client.get("/openapi/api-keys"))
    assert any(item["id"] == str(api_key_id) for item in listing["data"]["list"])

    assert_success(
        client.post(
            f"/openapi/api-keys/{api_key_id}",
            json={"is_active": True, "remark": "updated"},
        )
    )
    db_session.expire_all()
    assert db_session.get(ApiKey, api_key_id).remark == "updated"

    assert_success(
        client.post(
            f"/openapi/api-keys/{api_key_id}/is-active",
            json={"is_active": False},
        )
    )
    db_session.expire_all()
    assert db_session.get(ApiKey, api_key_id).is_active is False

    assert_success(client.post(f"/openapi/api-keys/{api_key_id}/delete"))
    db_session.expire_all()
    assert db_session.get(ApiKey, api_key_id) is None


def test_api_tool_crud_routes_persist_and_query(client, account, db_session):
    from internal.model import ApiTool, ApiToolProvider

    payload = {
        "name": "integration-tools",
        "icon": "https://example.com/tool.png",
        "openapi_schema": OPENAPI_SCHEMA,
        "headers": [{"key": "Authorization", "value": "Bearer test"}],
    }
    assert_success(client.post("/api-tools/validate-openapi-schema", json=payload))
    assert_success(client.post("/api-tools", json=payload))
    provider = (
        db_session.query(ApiToolProvider)
        .filter_by(account_id=account.id, name="integration-tools")
        .one()
    )
    tool = db_session.query(ApiTool).filter_by(provider_id=provider.id).one()

    assert_success(client.get("/api-tools", query_string={"search_word": "integration"}))
    assert_success(client.get(f"/api-tools/{provider.id}"))
    assert_success(client.get(f"/api-tools/{provider.id}/tools/{tool.name}"))

    updated = {**payload, "name": "updated-tools"}
    assert_success(client.post(f"/api-tools/{provider.id}", json=updated))
    db_session.expire_all()
    assert db_session.get(ApiToolProvider, provider.id).name == "updated-tools"

    assert_success(client.post(f"/api-tools/{provider.id}/delete"))
    db_session.expire_all()
    assert db_session.get(ApiToolProvider, provider.id) is None


def test_dataset_crud_routes_persist_and_query(
    client, account, db_session, handler_for
):
    from internal.model import Dataset

    assert_success(client.post("/datasets", json=DATASET_PAYLOAD))
    record = (
        db_session.query(Dataset)
        .filter_by(account_id=account.id, name="integration-dataset")
        .one()
    )
    dataset_id = record.id

    assert_success(client.get(f"/datasets/{dataset_id}"))
    listing = assert_success(
        client.get("/datasets", query_string={"search_word": "integration"})
    )
    assert any(item["id"] == str(dataset_id) for item in listing["data"]["list"])

    updated = {**DATASET_PAYLOAD, "name": "updated-integration-dataset"}
    assert_success(client.post(f"/datasets/{dataset_id}", json=updated))
    db_session.expire_all()
    assert db_session.get(Dataset, dataset_id).name == "updated-integration-dataset"

    queries = assert_success(client.get(f"/datasets/{dataset_id}/queries"))
    assert queries["data"] == []

    dataset_handler = handler_for("delete_dataset")
    dataset_handler.dataset_service.indexing_service.delete_dataset = lambda *args: None
    assert_success(client.post(f"/datasets/{dataset_id}/delete"))
    db_session.expire_all()
    assert db_session.get(Dataset, dataset_id) is None


def test_workflow_crud_and_graph_routes_persist_and_query(
    client, account, db_session
):
    from internal.model import Workflow

    created = assert_success(client.post("/workflows", json=WORKFLOW_PAYLOAD))
    workflow_id = UUID(created["data"]["workflow_id"])
    assert db_session.get(Workflow, workflow_id) is not None

    assert_success(client.get(f"/workflows/{workflow_id}"))
    listing = assert_success(
        client.get("/workflows", query_string={"search_word": "integration"})
    )
    assert any(item["id"] == str(workflow_id) for item in listing["data"]["list"])

    updated = {**WORKFLOW_PAYLOAD, "name": "updated-integration-workflow"}
    assert_success(client.post(f"/workflows/{workflow_id}", json=updated))
    db_session.expire_all()
    assert db_session.get(Workflow, workflow_id).name == "updated-integration-workflow"

    graph = VALID_WORKFLOW_GRAPH
    assert_success(client.post(f"/workflows/{workflow_id}/draft-graph", json=graph))
    draft = assert_success(client.get(f"/workflows/{workflow_id}/draft-graph"))
    assert len(draft["data"]["nodes"]) == 2
    assert len(draft["data"]["edges"]) == 1

    workflow = db_session.get(Workflow, workflow_id)
    workflow.is_debug_passed = True
    db_session.flush()
    assert_success(client.post(f"/workflows/{workflow_id}/publish"))
    db_session.expire_all()
    assert db_session.get(Workflow, workflow_id).status == "published"
    assert_success(client.post(f"/workflows/{workflow_id}/cancel-publish"))

    assert_success(client.post(f"/workflows/{workflow_id}/delete"))
    db_session.expire_all()
    assert db_session.get(Workflow, workflow_id) is None
