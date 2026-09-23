from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from internal.core.language_model import LanguageModelManager
from internal.exception import ValidateErrorException
from internal.service.faiss_service import FaissService


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_model_parameters_rejected(value):
    with pytest.raises(ValidateErrorException):
        LanguageModelManager().validate_model_config({
            "provider": "openai", "model": "gpt-4o-mini", "parameters": {"temperature": value}})


@pytest.mark.parametrize("attempts", [True, 1.5, "2", None, 0])
def test_structured_attempts_require_positive_integer(attempts, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    with pytest.raises(ValidateErrorException):
        LanguageModelManager().create_structured_chat_model(
            {"provider": "openai", "model": "gpt-4o-mini"}, BaseModel, max_attempts=attempts)


def test_faiss_initialization_is_lazy_and_concurrent_load_is_once(monkeypatch):
    loader = Mock(return_value=object())
    monkeypatch.setattr("internal.service.faiss_service.FAISS.load_local", loader)
    service = FaissService(SimpleNamespace(embeddings=object()))
    loader.assert_not_called()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.faiss, range(8)))
    assert all(result is results[0] for result in results)
    loader.assert_called_once()


def test_faiss_failed_load_can_be_retried(monkeypatch):
    expected = object()
    loader = Mock(side_effect=[OSError("missing index"), expected])
    monkeypatch.setattr("internal.service.faiss_service.FAISS.load_local", loader)
    service = FaissService(SimpleNamespace(embeddings=object()))
    with pytest.raises(OSError):
        _ = service.faiss
    assert service.faiss is expected


@pytest.mark.parametrize("provider,model,key", [
    ("openai", "gpt-4o-mini", "OPENAI_API_KEY"),
    ("deepseek", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
    ("moonshot", "kimi-k3", "MOONSHOT_API_KEY"),
    ("doubao", "doubao-seed-2-0-pro-260215", "ARK_API_KEY"),
    ("zhipu", "glm-5.2", "ZHIPU_API_KEY"),
])
def test_remote_model_has_bounded_transport_without_sdk_retry(monkeypatch, provider, model, key):
    monkeypatch.setenv(key, "offline-fake-key")
    llm = LanguageModelManager().create_language_model({"provider": provider, "model": model})
    assert llm.request_timeout == 60
    assert llm.max_retries == 0


def test_ollama_has_explicit_timeout():
    llm = LanguageModelManager().create_language_model({"provider": "ollama", "model": "qwen2.5-7b"})
    assert llm.client_kwargs["timeout"] == 60


@pytest.mark.parametrize("failure,expected_calls", [(ValueError, 1), (TimeoutError, 1)])
def test_structured_model_does_not_retry_transport_or_unrelated_errors(monkeypatch, failure, expected_calls):
    from langchain_core.runnables import RunnableLambda
    class Result(BaseModel):
        answer: str
    call = Mock(side_effect=failure("offline"))
    fake = SimpleNamespace(with_structured_output=lambda *args, **kwargs: RunnableLambda(call))
    monkeypatch.setattr(LanguageModelManager, "create_language_model", lambda *args: fake)
    chain = LanguageModelManager().create_structured_chat_model(
        {"provider": "openai", "model": "gpt-4o-mini"}, Result)
    with pytest.raises(failure):
        chain.invoke("question")
    assert call.call_count == expected_calls


def test_structured_invalid_output_stops_after_attempt_limit(monkeypatch):
    from langchain_core.runnables import RunnableLambda
    from pydantic import ValidationError
    class Result(BaseModel):
        answer: str
    call = Mock(return_value={"wrong": "value"})
    fake = SimpleNamespace(with_structured_output=lambda *args, **kwargs: RunnableLambda(call))
    monkeypatch.setattr(LanguageModelManager, "create_language_model", lambda *args: fake)
    chain = LanguageModelManager().create_structured_chat_model(
        {"provider": "openai", "model": "gpt-4o-mini"}, Result, max_attempts=2)
    with pytest.raises(ValidationError):
        chain.invoke("question")
    assert call.call_count == 2


def test_embedding_cache_failure_does_not_publish_partial_instance(monkeypatch):
    from internal.service.embeddings_service import EmbeddingsService
    from threading import Lock
    service = object.__new__(EmbeddingsService)
    service._embeddings = service._cache_backed_embeddings = None
    service._lock, service._store = Lock(), Mock()
    service._model_path, service._base_cache_dir = "fake-model", "fake-cache"
    monkeypatch.setattr(service, "_get_device", lambda: "cpu")
    base, cached = Mock(), Mock()
    monkeypatch.setattr("internal.service.embeddings_service.HuggingFaceEmbeddings", Mock(return_value=base))
    cache = Mock(side_effect=[ValueError("cache initialization"), cached])
    monkeypatch.setattr("internal.service.embeddings_service.CacheBackedEmbeddings.from_bytes_store", cache)
    with pytest.raises(ValueError):
        _ = service.embeddings
    assert service._embeddings is None and service._cache_backed_embeddings is None
    assert service.cache_backed_embeddings is cached
    assert service.embeddings is base


def test_legacy_model_service_uses_factory_and_instance_fallback():
    from internal.service.language_model_service import LanguageModelService
    manager = Mock()
    service = LanguageModelService(Mock(), manager)
    config = {"provider": "openai", "model": "gpt-4o-mini"}
    assert service.load_language_model(config) is manager.create_language_model.return_value
    manager.validate_model_config.side_effect = ValidateErrorException("invalid")
    assert service.load_language_model({}) is manager.create_default_language_model.return_value


def test_model_missing_optional_sdk_is_explicit(monkeypatch):
    from internal.core.language_model.entities.provider_entity import Provider
    monkeypatch.setattr(Provider, "get_model_class", lambda *args: Mock(side_effect=ImportError("missing")))
    with pytest.raises(ValidateErrorException, match="可选SDK"):
        LanguageModelManager().create_language_model({"provider": "tongyi", "model": "qwen-plus"})
