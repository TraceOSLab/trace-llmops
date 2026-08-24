from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from pkg.response import Response
from test.integration.conftest import assert_success
from test.integration.handler.test_database_http_routes import (
    DATASET_PAYLOAD,
    VALID_WORKFLOW_GRAPH,
    WORKFLOW_PAYLOAD,
)


pytestmark = pytest.mark.integration


def test_oauth_routes_use_real_http_and_schema(client, anonymous_client, handler_for):
    handler = handler_for("provider")
    oauth = MagicMock()
    oauth.get_authorization_url.return_value = "https://example.com/oauth"
    handler.oauth_service.get_oauth_by_provider_name = MagicMock(return_value=oauth)
    handler.oauth_service.oauth_login = MagicMock(
        return_value={"access_token": "test-token", "expire_at": 123}
    )

    provider = assert_success(anonymous_client.get("/oauth/github"))
    assert provider["data"]["redirect_uri"] == "https://example.com/oauth"
    authorized = assert_success(
        anonymous_client.post("/oauth/authorize/github", json={"code": "test-code"})
    )
    assert authorized["data"]["access_token"] == "test-token"


def test_builtin_app_routes(client, handler_for):
    handler = handler_for("get_builtin_app_categories")
    handler.builtin_app_service.get_categories = MagicMock(return_value=[])
    handler.builtin_app_service.get_builtin_apps = MagicMock(return_value=[])
    handler.builtin_app_service.add_builtin_app_to_space = MagicMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    assert_success(client.get("/builtin-apps/categories"))
    assert_success(client.get("/builtin-apps"))
    assert_success(
        client.post(
            "/builtin-apps/add-builtin-app-to-space",
            json={"builtin_app_id": str(uuid4())},
        )
    )


def test_builtin_tool_routes(client, handler_for):
    handler = handler_for("get_builtin_tools")
    handler.builtin_tool_service.get_builtin_tools = MagicMock(return_value=[])
    handler.builtin_tool_service.get_categories = MagicMock(return_value=[])
    handler.builtin_tool_service.get_provider_tool = MagicMock(
        return_value={"name": "search"}
    )
    handler.builtin_tool_service.get_provider_icon = MagicMock(
        return_value=(b"png", "image/png")
    )
    assert_success(client.get("/builtin-tools"))
    assert_success(client.get("/builtin-tools/categories"))
    assert_success(client.get("/builtin-tools/google/tools/search"))
    icon = client.get("/builtin-tools/google/icon")
    assert icon.status_code == 200 and icon.mimetype == "image/png"


def test_upload_routes_use_multipart_without_cos(client, handler_for):
    handler = handler_for("upload_file")
    upload_record = SimpleNamespace(
        id=uuid4(),
        account_id=uuid4(),
        name="file.txt",
        key="test/file.txt",
        size=4,
        extension="txt",
        mime_type="text/plain",
        created_at=datetime.now(),
    )
    handler.cos_service.upload_file = MagicMock(return_value=upload_record)
    handler.cos_service.get_file_url = MagicMock(
        return_value="https://example.com/image.png"
    )
    uploaded = assert_success(
        client.post(
            "/upload-files/file",
            data={"file": (BytesIO(b"text"), "file.txt")},
            content_type="multipart/form-data",
        )
    )
    assert uploaded["data"]["name"] == "file.txt"
    image = assert_success(
        client.post(
            "/upload-files/image",
            data={"file": (BytesIO(b"png"), "image.png")},
            content_type="multipart/form-data",
        )
    )
    assert image["data"]["image_url"].startswith("https://example.com")


def test_ai_routes_never_call_models(client, handler_for):
    handler = handler_for("optimize_prompt")
    handler.ai_service.optimize_prompt = MagicMock(
        return_value=iter(["event: answer\ndata: optimized\n\n"])
    )
    handler.ai_service.generate_suggested_questions_from_message_id = MagicMock(
        return_value=["question"]
    )
    optimized = client.post("/ai/optimize-prompt", json={"prompt": "draft"})
    assert optimized.mimetype == "text/event-stream"
    assert b"optimized" in optimized.get_data()
    questions = assert_success(
        client.post(
            "/ai/suggested-questions", json={"message_id": str(uuid4())}
        )
    )
    assert questions["data"] == ["question"]


def test_dataset_hit_uses_real_dataset_and_fake_retrieval(
    client, db_session, handler_for
):
    from internal.model import Dataset

    assert_success(client.post("/datasets", json=DATASET_PAYLOAD))
    dataset = db_session.query(Dataset).filter_by(name="integration-dataset").one()
    handler = handler_for("hit")
    handler.dataset_service.retrieval_service.search_in_datasets = MagicMock(
        return_value=[]
    )
    result = assert_success(
        client.post(
            f"/datasets/{dataset.id}/hit",
            json={
                "query": "hello",
                "retrieval_strategy": "semantic",
                "k": 3,
                "score": 0.5,
            },
        )
    )
    assert result["data"] == []


def test_openapi_chat_uses_api_key_and_fake_model(client, account, db_session, app, handler_for):
    from internal.model import ApiKey

    key = ApiKey(
        id=uuid4(),
        account_id=account.id,
        api_key="llmops-v1/integration",
        is_active=True,
        remark="integration",
    )
    db_session.add(key)
    db_session.flush()
    handler = handler_for("chat", blueprint="openapi")
    handler.openapi_service.chat = MagicMock(
        return_value=iter(["event: done\ndata: {}\n\n"])
    )
    response = app.test_client().post(
        "/openapi/chat",
        headers={"Authorization": "Bearer llmops-v1/integration"},
        json={
            "app_id": str(uuid4()),
            "end_user_id": str(uuid4()),
            "conversation_id": "",
            "query": "hello",
            "stream": True,
        },
    )
    assert response.mimetype == "text/event-stream"
    assert b"event: done" in response.get_data()


def test_workflow_debug_stream_uses_fake_runtime(client, db_session, handler_for, monkeypatch):
    import internal.service.workflow_service as workflow_service_module
    from internal.model import Workflow

    created = assert_success(client.post("/workflows", json=WORKFLOW_PAYLOAD))
    workflow_id = UUID(created["data"]["workflow_id"])
    assert_success(
        client.post(
            f"/workflows/{workflow_id}/draft-graph", json=VALID_WORKFLOW_GRAPH
        )
    )

    runtime = MagicMock()
    runtime.stream.return_value = iter([])
    monkeypatch.setattr(workflow_service_module, "WorkflowTool", lambda *args, **kwargs: runtime)
    response = client.post(f"/workflows/{workflow_id}/debug", json={})
    assert response.mimetype == "text/event-stream"
    response.get_data()
    db_session.expire_all()
    assert db_session.get(Workflow, workflow_id).is_debug_passed is True


def test_language_model_routes_use_local_service_boundary(client, handler_for):
    handler = handler_for("get_language_models")
    handler.language_model_service.get_language_models = MagicMock(return_value=[])
    handler.language_model_service.get_language_model = MagicMock(
        return_value={"name": "model"}
    )
    handler.language_model_service.get_language_model_icon = MagicMock(
        return_value=(b"svg", "image/svg+xml")
    )
    assert_success(client.get("/language-models"))
    assert_success(client.get("/language-models/openai/model"))
    icon = client.get("/language-models/openai/icon")
    assert icon.status_code == 200 and icon.mimetype == "image/svg+xml"
