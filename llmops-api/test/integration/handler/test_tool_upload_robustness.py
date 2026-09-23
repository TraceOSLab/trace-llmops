from io import BytesIO
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from internal.model import ApiTool, ApiToolProvider
from internal.model.upload_file import UploadFile
from test.integration.conftest import assert_success
from test.integration.handler.test_database_http_routes import OPENAPI_SCHEMA

pytestmark = pytest.mark.integration

PAYLOAD = {"name": "tools-atomic", "icon": "https://example.com/icon.png",
           "headers": [], "openapi_schema": OPENAPI_SCHEMA}


def test_delete_tool_provider_keeps_other_accounts_and_providers(client, db_session, account, other_account):
    assert_success(client.post("/api-tools", json=PAYLOAD))
    target = db_session.query(ApiToolProvider).filter_by(name=PAYLOAD["name"]).one()
    for owner, name in [(account, "same-account"), (other_account, "other-account")]:
        provider = ApiToolProvider(account_id=owner.id, name=name)
        db_session.add(provider)
        db_session.flush()
        db_session.add(ApiTool(provider_id=provider.id, account_id=owner.id, name=name))
    db_session.commit()
    assert_success(client.post(f"/api-tools/{target.id}/delete"))
    assert db_session.query(ApiTool).filter(ApiTool.name.in_(["same-account", "other-account"])).count() == 2


@pytest.mark.parametrize("update", [False, True])
def test_tool_write_failure_rolls_back_whole_provider(client, db_session, update):
    endpoint = "/api-tools"
    if update:
        assert_success(client.post(endpoint, json=PAYLOAD))
        original = db_session.query(ApiToolProvider).filter_by(name=PAYLOAD["name"]).one()
        endpoint += f"/{original.id}"
        old_tool_ids = [row.id for row in db_session.query(ApiTool).filter_by(provider_id=original.id)]

    def fail(*args):
        raise RuntimeError("insert tool failed")

    event.listen(ApiTool, "before_insert", fail)
    try:
        result = client.post(endpoint, json={**PAYLOAD, "name": "changed-tools"})
        assert result.get_json()["code"] == "fail"
    finally:
        event.remove(ApiTool, "before_insert", fail)
    db_session.expire_all()
    assert db_session.query(ApiToolProvider).filter_by(name="changed-tools").count() == 0
    if update:
        assert original.name == PAYLOAD["name"]
        assert [row.id for row in db_session.query(ApiTool).filter_by(provider_id=original.id)] == old_tool_ids


@pytest.mark.parametrize("failure", [None, "cos", "database"])
def test_upload_uses_real_database_and_compensates(client, db_session, handler_for, monkeypatch, failure):
    service = handler_for("upload_file").cos_service
    cos = Mock()
    monkeypatch.setattr(service, "_get_client", lambda: cos)
    monkeypatch.setattr(service, "_get_bucket", lambda: "isolated-test")
    if failure == "cos":
        cos.put_object.side_effect = TimeoutError()
    def fail(*args):
        raise RuntimeError("record failed")
    if failure == "database":
        event.listen(UploadFile, "before_insert", fail)
    try:
        result = client.post("/upload-files/file", data={"file": (BytesIO(b"content"), "record.txt")})
    finally:
        if failure == "database":
            event.remove(UploadFile, "before_insert", fail)
    if failure:
        assert result.get_json()["code"] == "fail"
        assert db_session.query(UploadFile).filter_by(name="record.txt").count() == 0
        if failure == "database":
            cos.delete_object.assert_called_once()
    else:
        data = assert_success(result)["data"]
        record = db_session.query(UploadFile).filter_by(key=data["key"]).one()
        assert record.size == 7 and record.extension == "txt"
        assert set(data) == {"id", "account_id", "name", "key", "size", "extension", "mime_type", "created_at"}
