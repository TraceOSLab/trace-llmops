from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event

from internal.entity.app_entity import DEFAULT_APP_CONFIG
from internal.model import App, AppConfig, AppConfigVersion, AppDatasetJoin, Dataset
from test.integration.conftest import assert_success
from test.integration.handler.test_database_http_routes import APP_PAYLOAD

pytestmark = pytest.mark.integration


def create_app(client, db_session):
    data = assert_success(client.post("/apps", json=APP_PAYLOAD))["data"]
    return db_session.get(App, UUID(data["id"]))


@pytest.mark.parametrize("missing_field", ["provider", "model"])
def test_missing_model_is_resolved_without_rewriting_draft(client, db_session, missing_field):
    app = create_app(client, db_session)
    original = deepcopy(DEFAULT_APP_CONFIG["model_config"])
    original[missing_field] = "removed-from-catalog"
    app.draft_app_config.model_config = original
    db_session.commit()
    result = assert_success(client.get(f"/apps/{app.id}/draft-app-config"))["data"]
    assert result["model_config"]["provider"] == DEFAULT_APP_CONFIG["model_config"]["provider"]
    assert result["model_config"]["model"] == DEFAULT_APP_CONFIG["model_config"]["model"]
    db_session.expire_all()
    assert app.draft_app_config.model_config == original


@pytest.mark.parametrize("foreign_owner", [False, True])
def test_cannot_restore_another_apps_history(client, db_session, other_account, foreign_owner):
    own, other = create_app(client, db_session), create_app(client, db_session)
    assert_success(client.post(f"/apps/{other.id}/draft-app-config", json={"preset_prompt": "private-prompt"}))
    assert_success(client.post(f"/apps/{other.id}/publish"))
    history = db_session.query(AppConfigVersion).filter_by(app_id=other.id, config_type="published").one()
    if foreign_owner:
        other.account_id = other_account.id
        db_session.commit()
    response = client.post(f"/apps/{own.id}/fallback-history", json={"app_config_version_id": str(history.id)})
    assert response.get_json()["code"] in {"not_found", "forbidden"}
    db_session.expire_all()
    assert own.draft_app_config.preset_prompt == ""


def test_restore_requires_published_history(client, db_session):
    app = create_app(client, db_session)
    response = client.post(f"/apps/{app.id}/fallback-history", json={"app_config_version_id": str(app.draft_app_config.id)})
    assert response.get_json()["code"] == "not_found"


def test_publish_failure_keeps_previous_runtime_and_history(client, db_session, account):
    app = create_app(client, db_session)
    dataset = Dataset(id=uuid4(), account_id=account.id)
    db_session.add(dataset)
    db_session.commit()
    assert_success(client.post(f"/apps/{app.id}/draft-app-config", json={"datasets": [str(dataset.id)], "preset_prompt": "old"}))
    assert_success(client.post(f"/apps/{app.id}/publish"))
    old_config_id = app.app_config_id
    old_config_count = db_session.query(AppConfig).filter_by(app_id=app.id).count()
    assert_success(client.post(f"/apps/{app.id}/draft-app-config", json={"datasets": [], "preset_prompt": "new"}))

    def fail_history(mapper, connection, target):
        if target.config_type == "published":
            raise RuntimeError("history write failed")

    event.listen(AppConfigVersion, "before_insert", fail_history)
    try:
        assert client.post(f"/apps/{app.id}/publish").get_json()["code"] == "fail"
    finally:
        event.remove(AppConfigVersion, "before_insert", fail_history)
    db_session.expire_all()
    assert app.app_config_id == old_config_id
    assert app.app_config.preset_prompt == "old"
    assert db_session.query(AppConfig).filter_by(app_id=app.id).count() == old_config_count
    assert db_session.query(AppConfigVersion).filter_by(app_id=app.id, config_type="published").count() == 1
    assert db_session.query(AppDatasetJoin).filter_by(app_id=app.id, dataset_id=dataset.id).count() == 1


def test_copy_and_history_are_independent(client, db_session):
    app = create_app(client, db_session)
    assert_success(client.post(f"/apps/{app.id}/draft-app-config", json={"opening_questions": ["original"]}))
    assert_success(client.post(f"/apps/{app.id}/publish"))
    app.token = "original-web-token"
    db_session.commit()
    copy_id = UUID(assert_success(client.post(f"/apps/{app.id}/copy"))["data"]["id"])
    copied = db_session.get(App, copy_id)
    assert copied.token != app.token
    assert copied.app_config_id is None and copied.status == "draft"
    assert_success(client.post(f"/apps/{copy_id}/draft-app-config", json={"opening_questions": ["copy"]}))
    db_session.expire_all()
    assert app.draft_app_config.opening_questions == ["original"]
    history = db_session.query(AppConfigVersion).filter_by(app_id=app.id, config_type="published").one()
    assert history.opening_questions == ["original"]


def test_builtin_template_creates_correct_draft_link(client, db_session, handler_for):
    manager = handler_for("add_builtin_app_to_space").builtin_app_service.builtin_app_manager
    template = manager.get_builtin_apps()[0]
    response = assert_success(client.post("/builtin-apps/add-builtin-app-to-space", json={"builtin_app_id": template.id}))
    app_id = UUID(response["data"]["id"])
    record = db_session.get(App, app_id)
    assert record.app_config_id is None
    assert record.draft_app_config_id == record.draft_app_config.id
    assert record.draft_app_config.preset_prompt == template.preset_prompt


@pytest.mark.parametrize("payload", [
    {"model_config": {"provider": "openai", "model": "gpt-4o-mini", "parameters": []}},
    {"workflows": [{}]}, {"workflows": ["invalid-uuid"]},
    {"tools": [{"type": "api_tool", "provider_id": "invalid-uuid", "tool_id": "tool", "params": {}}]},
    {"dialog_round": True},
])
def test_invalid_draft_input_returns_validation_error(client, db_session, payload):
    app = create_app(client, db_session)
    assert client.post(f"/apps/{app.id}/draft-app-config", json=payload).get_json()["code"] == "validate_error"


def test_web_app_token_is_persisted_rotated_and_cleared(client, db_session):
    app = create_app(client, db_session)
    path = f"/apps/{app.id}/published-config"
    assert assert_success(client.get(path))["data"]["web_app"]["token"] == ""
    assert_success(client.post(f"/apps/{app.id}/publish"))
    old_token = assert_success(client.get(path))["data"]["web_app"]["token"]
    db_session.expire_all()
    assert app.token == old_token and old_token
    assert_success(client.get(f"/web-apps/{old_token}"))
    new_token = assert_success(client.post(f"{path}/regenerate-web-app-token"))["data"]["token"]
    db_session.expire_all()
    assert app.token == new_token and new_token != old_token
    assert client.get(f"/web-apps/{old_token}").get_json()["code"] != "success"
    assert_success(client.post(f"/apps/{app.id}/cancel-publish"))
    db_session.expire_all()
    assert app.token is None
    assert client.get(f"/web-apps/{new_token}").get_json()["code"] != "success"


def test_delete_cleans_app_configuration_rows(client, db_session):
    app = create_app(client, db_session)
    app_id = app.id
    assert_success(client.post(f"/apps/{app_id}/publish"))
    assert_success(client.post(f"/apps/{app_id}/delete"))
    assert db_session.get(App, app_id) is None
    for model in (AppConfig, AppConfigVersion, AppDatasetJoin):
        assert db_session.query(model).filter_by(app_id=app_id).count() == 0


def test_cancel_failure_keeps_published_state(client, db_session):
    app = create_app(client, db_session)
    assert_success(client.post(f"/apps/{app.id}/publish"))
    config_id = app.app_config_id
    connection = db_session.get_bind()

    def fail_join_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM app_dataset_join"):
            raise RuntimeError("join cleanup failed")

    event.listen(connection, "before_cursor_execute", fail_join_delete)
    try:
        assert client.post(f"/apps/{app.id}/cancel-publish").get_json()["code"] == "fail"
    finally:
        event.remove(connection, "before_cursor_execute", fail_join_delete)
    db_session.expire_all()
    assert app.status == "published" and app.app_config_id == config_id


def test_foreign_references_are_hidden_without_rewriting_snapshots(client, db_session, other_account, handler_for):
    from internal.model import ApiTool, ApiToolProvider, Workflow

    app = create_app(client, db_session)
    dataset = Dataset(id=uuid4(), account_id=other_account.id)
    workflow = Workflow(id=uuid4(), account_id=other_account.id, status="published")
    provider = ApiToolProvider(id=uuid4(), account_id=other_account.id)
    tool = ApiTool(id=uuid4(), account_id=other_account.id, provider_id=provider.id, name="foreign_tool")
    db_session.add_all([dataset, workflow, provider, tool])
    values = deepcopy(DEFAULT_APP_CONFIG)
    values.update(datasets=[str(dataset.id)], workflows=[str(workflow.id)], tools=[{
        "type": "api_tool", "provider_id": str(provider.id), "tool_id": tool.name, "params": {},
    }])
    draft = app.draft_app_config
    for key, value in values.items():
        setattr(draft, key, value)
    runtime = AppConfig(app_id=app.id, **{key: value for key, value in values.items() if key != "datasets"})
    db_session.add(runtime)
    db_session.flush()
    app.app_config_id = runtime.id
    app.status = "published"
    db_session.add(AppDatasetJoin(app_id=app.id, dataset_id=dataset.id))
    db_session.commit()
    response = assert_success(client.get(f"/apps/{app.id}/draft-app-config"))["data"]
    service = handler_for("get_draft_app_config").app_service.app_config_service
    published = service.get_app_config(app)
    for config in (response, published):
        assert config["datasets"] == config["workflows"] == config["tools"] == []
    db_session.expire_all()
    assert draft.datasets == [str(dataset.id)]  # GET must not rewrite source snapshots.
    assert db_session.query(AppDatasetJoin).filter_by(app_id=app.id).count() == 1
    # Publishing performs the write-side cleanup and leaves the source snapshot independent.
    assert_success(client.post(f"/apps/{app.id}/publish"))
    db_session.expire_all()
    assert app.draft_app_config.datasets == []
    assert db_session.query(AppDatasetJoin).filter_by(app_id=app.id).count() == 0


def test_removed_dataset_is_filtered_on_restore_without_modifying_history(client, db_session, account):
    app = create_app(client, db_session)
    dataset = Dataset(id=uuid4(), account_id=account.id)
    db_session.add(dataset)
    db_session.commit()
    dataset_id = str(dataset.id)
    assert_success(client.post(f"/apps/{app.id}/draft-app-config", json={"datasets": [dataset_id]}))
    assert_success(client.post(f"/apps/{app.id}/publish"))
    history = db_session.query(AppConfigVersion).filter_by(app_id=app.id, config_type="published").one()
    db_session.delete(dataset)
    db_session.commit()
    assert_success(client.post(f"/apps/{app.id}/fallback-history", json={"app_config_version_id": str(history.id)}))
    db_session.expire_all()
    assert app.draft_app_config.datasets == []
    assert history.datasets == [dataset_id]
