"""外部 HTTP 边界使用 Fake；不访问网络，也不重试带副作用的请求。"""
from unittest.mock import Mock, PropertyMock
from uuid import uuid4

import pytest
import requests
from pydantic import ValidationError

from internal.core.tools.api_tools.entities import ToolEntity
from internal.core.tools.api_tools.providers.api_provider_manager import ApiProviderManager
from internal.core.workflow.nodes.http_request.http_request_entity import HttpRequestNodeData
from internal.core.workflow.nodes.http_request.http_request_node import HttpRequestNode
from pkg.oauth.github_oauth import GithubOAuth


def response(payload=None, status=200):
    result = Mock()
    result.text = "upstream body"
    result.status_code = status
    result.json.return_value = payload
    return result


def test_tool_optional_field_can_be_omitted_but_required_field_cannot():
    schema = ApiProviderManager._create_model_from_parameters([
        {"name": "required", "type": "string", "required": True},
        {"name": "optional", "type": "string", "required": False},
    ])
    assert schema(required="ok").optional is None
    with pytest.raises(ValidationError):
        schema()


def test_tool_preserves_response_text_and_closes_response(monkeypatch):
    upstream = response(status=422)
    request = Mock(return_value=upstream)
    monkeypatch.setattr(requests, "request", request)
    entity = ToolEntity(url="http://127.0.0.1/actions", method="post")
    assert ApiProviderManager._create_tool_func_from_tool_entity(entity)() == "upstream body"
    assert request.call_args.kwargs["timeout"] == (5, 30)
    upstream.close.assert_called_once()
    request.assert_called_once()


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete", "head", "options"])
def test_http_node_preserves_status_and_closes_response(monkeypatch, method):
    upstream = response(status=503)
    request = Mock(return_value=upstream)
    monkeypatch.setattr(requests, method, request)
    node = HttpRequestNode(node_data=HttpRequestNodeData(
        id=uuid4(), node_type="http_request", url="http://127.0.0.1/action", method=method,
    ))
    result = node.invoke({})["node_results"][0]
    assert result.outputs == {"text": "upstream body", "status_code": 503}
    assert request.call_args.kwargs["timeout"] == (5, 30)
    assert isinstance(request.call_args.args[0], str)
    upstream.close.assert_called_once()


@pytest.mark.parametrize("boundary", ["tool", "node", "oauth"])
@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_transport_failure_is_not_retried(monkeypatch, boundary, error):
    request = Mock(side_effect=error("offline failure"))
    if boundary == "tool":
        monkeypatch.setattr(requests, "request", request)
        invoke = ApiProviderManager._create_tool_func_from_tool_entity(
            ToolEntity(url="http://127.0.0.1/actions", method="post"))
    elif boundary == "node":
        monkeypatch.setattr(requests, "post", request)
        node = HttpRequestNode(node_data=HttpRequestNodeData(
            id=uuid4(), node_type="http_request", url="http://127.0.0.1/action", method="post"))
        invoke = lambda: node.invoke({})
    else:
        monkeypatch.setattr(requests, "post", request)
        invoke = lambda: GithubOAuth("id", "secret", "http://localhost").get_access_token("code")
    with pytest.raises(error):
        invoke()
    request.assert_called_once()
    assert request.call_args.kwargs["timeout"] == (5, 30)


@pytest.mark.parametrize("payload", [[], None, {"access_token": 12}, {"error": "secret-value"}])
def test_oauth_rejects_invalid_token_payload_without_echoing_it(monkeypatch, payload):
    upstream = response(payload)
    monkeypatch.setattr(requests, "post", Mock(return_value=upstream))
    with pytest.raises(ValueError) as caught:
        GithubOAuth("id", "secret", "http://localhost").get_access_token("code")
    assert "secret-value" not in str(caught.value)
    upstream.close.assert_called_once()


@pytest.mark.parametrize("failure", ["status", "json"])
def test_oauth_closes_response_on_decode_or_status_error(monkeypatch, failure):
    upstream = response()
    if failure == "status":
        upstream.raise_for_status.side_effect = requests.HTTPError("rejected")
    else:
        upstream.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(requests, "post", Mock(return_value=upstream))
    with pytest.raises((requests.HTTPError, ValueError)):
        GithubOAuth("id", "secret", "http://localhost").get_access_token("code")
    upstream.close.assert_called_once()


def test_oauth_user_and_email_responses_are_closed(monkeypatch):
    responses = [response({"id": 42}), response([
        {"primary": True, "verified": True, "email": "owner@example.com"}])]
    request = Mock(side_effect=responses)
    monkeypatch.setattr(requests, "get", request)
    assert GithubOAuth("id", "secret", "http://localhost").get_user_info("token").id == "42"
    for upstream in responses:
        upstream.close.assert_called_once()
    assert all(call.kwargs["timeout"] == (5, 30) for call in request.call_args_list)


@pytest.mark.parametrize("user,emails", [([], []), ({"id": 42}, {}),
    ({"id": 42}, [None, {"primary": True, "verified": True, "email": 12}])])
def test_oauth_rejects_malformed_identity_payload(monkeypatch, user, emails):
    upstream = [response(user), response(emails)]
    request = Mock(side_effect=upstream)
    monkeypatch.setattr(requests, "get", request)
    with pytest.raises(ValueError):
        GithubOAuth("id", "secret", "http://localhost").get_user_info("token")
    for used in upstream[:request.call_count]:
        used.close.assert_called_once()


@pytest.mark.parametrize("boundary", ["tool", "node"])
def test_response_is_closed_when_reading_text_fails(monkeypatch, boundary):
    upstream = response()
    type(upstream).text = PropertyMock(side_effect=ValueError("decode failed"))
    request = Mock(return_value=upstream)
    if boundary == "tool":
        monkeypatch.setattr(requests, "request", request)
        invoke = ApiProviderManager._create_tool_func_from_tool_entity(ToolEntity(url="http://localhost"))
    else:
        monkeypatch.setattr(requests, "get", request)
        node = HttpRequestNode(node_data=HttpRequestNodeData(
            id=uuid4(), node_type="http_request", url="http://localhost"))
        invoke = lambda: node.invoke({})
    with pytest.raises(ValueError, match="decode failed"):
        invoke()
    upstream.close.assert_called_once()


@pytest.mark.parametrize("failure", [None, "district", "weather", "json"])
def test_weather_closes_session_and_responses_on_all_exits(monkeypatch, failure):
    from internal.core.tools.builtin_tools.providers.gaode.gaode_weather import GaodeWeatherTool

    monkeypatch.setenv("GAODE_API_KEY", "fake-key")
    district = response({"info": "OK", "districts": [{"adcode": "440100"}]})
    weather = response({"info": "OK", "forecasts": []})
    session = Mock()
    if failure == "district":
        session.request.side_effect = requests.Timeout("offline")
    elif failure == "weather":
        session.request.side_effect = [district, requests.Timeout("offline")]
    else:
        session.request.side_effect = [district, weather]
    if failure == "json":
        district.json.side_effect = ValueError("invalid json")
    monkeypatch.setattr(requests, "session", Mock(return_value=session))
    result = GaodeWeatherTool().invoke({"city": "广州"})
    assert ("失败" in result) == (failure is not None)
    session.close.assert_called_once()
    assert session.request.call_count == (2 if failure in (None, "weather") else 1)
    assert all(call.kwargs["timeout"] == (5, 30) for call in session.request.call_args_list)
    if failure != "district":
        district.close.assert_called_once()
    if failure is None:
        weather.close.assert_called_once()
