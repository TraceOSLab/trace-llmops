from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import jwt
import pytest
from flask import Flask
from werkzeug.datastructures import MultiDict

from internal.exception import UnauthorizedException
from internal.middleware.middleware import Middleware
from internal.server.http import Http
from internal.service.jwt_service import JWTService
from pkg.paginator import PaginatorReq
from pkg.password import compare_password
from pkg.response import validate_error_json
from pkg.sqlalchemy import SQLAlchemy


@pytest.mark.parametrize("changes", [
    {"exp": None}, {"iss": None}, {"sub": None}, {"iss": "other"},
    {"sub": "not-a-uuid"}, {"exp": 1},
])
def test_jwt_rejects_incomplete_or_invalid_claims(monkeypatch, changes):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-signing-at-least-32")
    payload = {"sub": str(uuid4()), "iss": "llmops", "exp": 4102444800}
    payload.update(changes)
    payload = {key: value for key, value in payload.items() if value is not None}
    token = JWTService.generate_token(payload)
    with pytest.raises(UnauthorizedException):
        JWTService.parse_token(token)


def test_jwt_accepts_existing_login_shape_and_rejects_wrong_signature(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-signing-at-least-32")
    payload = {"sub": str(uuid4()), "iss": "llmops", "exp": 4102444800}
    assert JWTService.parse_token(JWTService.generate_token(payload)) == payload
    token = jwt.encode(payload, "different-test-secret-key-at-least-32", algorithm="HS256")
    with pytest.raises(UnauthorizedException):
        JWTService.parse_token(token)


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "   ", "Basic abc", "Bearer a b"])
def test_malformed_bearer_is_an_authentication_error(header):
    with pytest.raises(UnauthorizedException):
        Middleware._validate_credential(SimpleNamespace(headers={"Authorization": header}))


@pytest.mark.parametrize("where", ["body", "commit"])
def test_auto_commit_rolls_back_and_preserves_failure(where):
    session = MagicMock()
    error = RuntimeError("failed transaction")
    if where == "commit":
        session.commit.side_effect = error
    with pytest.raises(RuntimeError) as captured:
        with SQLAlchemy.auto_commit(SimpleNamespace(session=session)):
            if where == "body":
                raise error
    assert captured.value is error
    session.rollback.assert_called_once_with()


def test_unhandled_error_does_not_expose_internal_detail(monkeypatch):
    monkeypatch.delenv("FLASK_ENV", raising=False)
    app = Flask(__name__)
    with app.app_context():
        response, status = Http._register_error_handler(app, RuntimeError("password=private-value"))
        assert status == 200
        assert response.get_json()["code"] == "fail"
        assert "private-value" not in response.get_data(as_text=True)


@pytest.mark.parametrize("errors", [None, {}, {"field": []}])
def test_empty_validation_errors_still_serialize(errors):
    with Flask(__name__).app_context():
        response, status = validate_error_json(errors)
        assert status == 200
        assert response.get_json()["code"] == "validate_error"


@pytest.mark.parametrize("value", ["", "0", "-1", "51", "abc"])
def test_pagination_rejects_explicit_invalid_size(value):
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_request_context():
        assert not PaginatorReq(MultiDict({"page_size": value})).validate()


def test_corrupt_password_storage_is_a_failed_comparison():
    assert compare_password("abcd1234", "broken-base64", "broken-base64") is False
