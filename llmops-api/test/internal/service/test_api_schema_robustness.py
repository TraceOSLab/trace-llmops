import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from internal.core.tools.api_tools.entities import ToolEntity
from internal.core.tools.api_tools.providers.api_provider_manager import ApiProviderManager
from internal.exception import ValidateErrorException
from internal.service.api_tool_service import ApiToolService

SCHEMA = {"server": "http://localhost:8080", "description": "internal tool", "paths": {
    "/search": {"get": {"operationId": "search", "description": "search"}}}}


def test_schema_allows_no_parameters_and_preserves_both_methods():
    schema = deepcopy(SCHEMA)
    schema["paths"]["/search"]["post"] = {"operationId": "create", "description": "create"}
    result = ApiToolService.parse_openapi_schema(json.dumps(schema))
    assert set(result.paths["/search"]) == {"get", "post"}


@pytest.mark.parametrize("paths", [{}, [], {"/": None}, {"/": {"get": []}},
    {"/": {"get": {"operationId": "", "description": "x", "parameters": []}}},
    {"/": {"get": {"operationId": "x", "description": "x", "parameters": [None]}}}])
def test_malformed_schema_is_validation_error(paths):
    with pytest.raises(ValidateErrorException):
        ApiToolService.parse_openapi_schema(json.dumps({**SCHEMA, "paths": paths}))


def test_tool_serializes_header_and_cookie_types_and_encodes_path(monkeypatch):
    response = Mock(text="ok")
    request = Mock(return_value=response)
    monkeypatch.setattr("requests.request", request)
    fn = ApiProviderManager._create_tool_func_from_tool_entity(ToolEntity(
        url="http://localhost/items/{item}", parameters=[
            {"name": "item", "in": "path"}, {"name": "count", "in": "header"},
            {"name": "session", "in": "cookie"}, {"name": "optional", "in": "header"}]))
    assert fn(item="a/b?c", count=3, session=7, optional=None) == "ok"
    args = request.call_args.kwargs
    assert args["url"] == "http://localhost/items/a%2Fb%3Fc"
    assert args["headers"] == {"count": "3"} and args["cookies"] == {"session": "7"}


@pytest.mark.parametrize("server", ["file:///etc/passwd", "http://", 1])
def test_invalid_server_is_validation_error(server):
    with pytest.raises(ValidateErrorException):
        ApiToolService.parse_openapi_schema(json.dumps({**SCHEMA, "server": server}))


@pytest.mark.parametrize("required,names", [(False, ["id"]), (True, ["id", "id"]), (True, ["wrong"])])
def test_invalid_path_parameters_rejected(required, names):
    schema = deepcopy(SCHEMA)
    operation = schema["paths"].pop("/search")["get"]
    operation["parameters"] = [{"name": name, "in": "path", "required": required,
                                "description": "id", "type": "str"} for name in names]
    schema["paths"]["/items/{id}"] = {"get": operation}
    with pytest.raises(ValidateErrorException):
        ApiToolService.parse_openapi_schema(json.dumps(schema))


@pytest.mark.parametrize("header", [{"key": "", "value": "x"}, {"key": "x", "value": 1},
    {"key": "x", "value": "ok\r\nX-Injected: bad"}])
def test_header_validation_rejects_nonstring_or_injected_value(header):
    from types import SimpleNamespace
    from wtforms.validators import ValidationError
    from internal.schema.api_tool_schema import CreateApiToolReq
    with pytest.raises(ValidationError):
        CreateApiToolReq.validate_headers(None, SimpleNamespace(data=[header]))
