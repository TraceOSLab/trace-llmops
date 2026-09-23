import asyncio
import builtins
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest
import requests

from internal.exception import ValidateErrorException
from internal.core.tools.builtin_tools.providers.dalle.dalle3 import dalle3
from internal.core.tools.builtin_tools.providers.google.google_serper import google_serper
from internal.core.tools.builtin_tools.providers.duckduckgo.duckduckgo_search import duckduckgo_search
from internal.core.tools.builtin_tools.providers.wikipedia.wikipedia_search import wikipedia_search


def test_dalle_forwards_style_and_has_no_sdk_retry(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    tool = dalle3(style="natural", size="1792x1024")
    fake = Mock()
    fake.generate.return_value = SimpleNamespace(data=[SimpleNamespace(url="https://example.com/image")])
    tool.api_wrapper.client = fake
    assert tool.invoke({"query": "a tree"}) == "https://example.com/image"
    assert fake.generate.call_args.kwargs["style"] == "natural"
    assert fake.generate.call_args.kwargs["size"] == "1792x1024"
    assert tool.api_wrapper.request_timeout == 60 and tool.api_wrapper.max_retries == 0


@pytest.mark.parametrize("failure", [None, "status", "json", "shape", "timeout"])
def test_serper_transport_and_parsing(monkeypatch, failure):
    monkeypatch.setenv("SERPER_API_KEY", "fake")
    response = Mock()
    response.json.return_value = {"organic": [{"snippet": "answer"}]}
    if failure == "status":
        response.raise_for_status.side_effect = requests.HTTPError()
    elif failure == "json":
        response.json.side_effect = ValueError()
    elif failure == "shape":
        response.json.return_value = []
    request = Mock(return_value=response)
    if failure == "timeout":
        request.side_effect = requests.Timeout()
    monkeypatch.setattr(requests, "post", request)
    tool = google_serper()
    if failure:
        with pytest.raises((ValueError, requests.RequestException)):
            tool.invoke({"query": "search"})
    else:
        assert tool.invoke({"query": "search"}) == "answer"
    request.assert_called_once()
    assert request.call_args.kwargs["timeout"] == (5, 30)
    if failure != "timeout":
        response.close.assert_called_once()


def test_serper_async_closes_owned_session_and_response(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "fake")
    response = Mock(json=AsyncMock(return_value={"organic": [{"snippet": "answer"}]}))
    response_context = AsyncMock()
    response_context.__aenter__.return_value = response
    session = Mock(post=Mock(return_value=response_context))
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    monkeypatch.setattr("aiohttp.ClientSession", Mock(return_value=session_context))
    result = asyncio.run(google_serper().ainvoke({"query": "search"}))
    assert result == "answer"
    response_context.__aexit__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()
    assert session.post.call_args.kwargs["timeout"].total == 35


@pytest.mark.parametrize("factory,module", [(duckduckgo_search, "ddgs"), (wikipedia_search, "wikipedia")])
def test_optional_tool_dependency_failure_is_explicit(monkeypatch, factory, module):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == module:
            raise ImportError("missing")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(ValidateErrorException, match=module):
        factory()


@pytest.mark.parametrize("params", [{"size": "invalid"}, {"style": "invalid"}])
def test_dalle_rejects_invalid_catalog_parameters(monkeypatch, params):
    from pydantic import ValidationError
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    with pytest.raises(ValidationError):
        dalle3(**params)


def test_builtin_catalog_inputs_and_all_icons():
    from pathlib import Path
    from flask import Flask
    from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
    from internal.core.tools.builtin_tools.categories import BuiltinCategoryManager
    from internal.service.builtin_tool_service import BuiltinToolService
    root = Path(__file__).resolve().parents[3]
    service = BuiltinToolService(BuiltinProviderManager(), BuiltinCategoryManager())
    with Flask("test", root_path=str(root / "app/http")).app_context():
        catalog = service.get_builtin_tools()
        assert len(catalog) == 6
        for provider in catalog:
            content, mime = service.get_provider_icon(provider["name"])
            assert content and mime.startswith("image/")
            for tool in provider["tools"]:
                detail = service.get_provider_tool(provider["name"], tool["name"])
                assert detail["inputs"] == tool["inputs"]


def test_current_time_tool_needs_no_network():
    from datetime import datetime
    from internal.core.tools.builtin_tools.providers.time.current_time import current_time
    value = current_time().invoke({})
    datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S")
