from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

from internal.core.language_model import LanguageModelManager
from internal.entity.conversation_entity import SuggestedQuestions
from internal.exception import ValidateErrorException


VISIBLE_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini"],
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "moonshot": ["kimi-k3", "kimi-k2.6"],
    "doubao": [
        "doubao-seed-2-0-pro-260215",
        "doubao-seed-2-0-lite-260215",
    ],
    "zhipu": ["glm-5.2", "glm-4.5-flash"],
    "ollama": ["qwen2.5-7b"],
}

PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "doubao": "ARK_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
}

STRUCTURED_OUTPUT_STRATEGIES = {
    "openai": ("json_schema", True),
    "deepseek": ("json_mode", False),
    "moonshot": ("function_calling", False),
    "doubao": ("function_calling", False),
    "zhipu": ("function_calling", False),
    "ollama": ("json_schema", False),
}


@pytest.fixture
def manager() -> LanguageModelManager:
    return LanguageModelManager()


def test_visible_provider_catalog_and_hidden_compatibility(manager):
    assert [provider.name for provider in manager.get_visible_providers()] == list(
        VISIBLE_MODELS
    )
    assert {
        provider.name: [
            model.model_name for model in provider.get_visible_model_entities()
        ]
        for provider in manager.get_visible_providers()
    } == VISIBLE_MODELS

    assert manager.get_provider("tongyi").provider_entity.visible is False
    assert manager.get_provider("wenxin").provider_entity.visible is False
    legacy_model = manager.get_provider("moonshot").get_model_entity(
        "moonshot-v1-8k"
    )
    assert legacy_model.visible is False


def test_visible_provider_icons_exist(manager):
    providers_path = Path(__file__).parents[4] / "internal/core/language_model/providers"

    for provider in manager.get_visible_providers():
        icon_path = (
            providers_path
            / provider.name
            / "_asset"
            / provider.provider_entity.icon
        )
        assert icon_path.is_file(), f"missing icon for {provider.name}"


@pytest.mark.parametrize("provider", list(VISIBLE_MODELS))
def test_factory_builds_provider_model_without_network(monkeypatch, manager, provider):
    if provider in PROVIDER_ENV:
        monkeypatch.setenv(PROVIDER_ENV[provider], "test-key")
    model_name = VISIBLE_MODELS[provider][0]
    temperature = 1 if provider == "moonshot" else 0.5

    llm = manager.create_chat_model(
        {
            "provider": provider,
            "model": model_name,
            "parameters": {"temperature": temperature},
        }
    )

    assert llm.temperature == temperature
    if provider == "deepseek":
        assert llm.model_name == model_name
        assert "langchain_deepseek" in type(llm).__mro__[1].__module__
    elif provider == "ollama":
        assert llm.model == "qwen2.5:7b"
        assert "langchain_ollama" in type(llm).__mro__[1].__module__
    else:
        assert llm.model_name == model_name
        assert "langchain_openai" in type(llm).__mro__[1].__module__


def test_ollama_maps_max_tokens_to_num_predict(manager):
    llm = manager.create_chat_model(
        {
            "provider": "ollama",
            "model": "qwen2.5-7b",
            "parameters": {"max_tokens": 1024},
        }
    )

    assert llm.num_predict == 1024


@pytest.mark.parametrize(
    ("provider", "expected_base_url"),
    [
        ("deepseek", "https://api.deepseek.com"),
        ("moonshot", "https://api.moonshot.cn/v1"),
        ("doubao", "https://ark.cn-beijing.volces.com/api/v3"),
        ("zhipu", "https://open.bigmodel.cn/api/paas/v4/"),
    ],
)
def test_factory_uses_provider_base_url(
    monkeypatch, manager, provider, expected_base_url
):
    monkeypatch.setenv(PROVIDER_ENV[provider], "test-key")
    llm = manager.create_chat_model(
        {"provider": provider, "model": VISIBLE_MODELS[provider][0]}
    )

    base_url = getattr(llm, "openai_api_base", None) or getattr(
        llm, "api_base", None
    )
    assert base_url == expected_base_url


def test_openai_base_url_can_be_overridden_by_environment(monkeypatch, manager):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://openai-proxy.example/v1")

    llm = manager.create_chat_model(
        {"provider": "openai", "model": "gpt-4o-mini"}
    )

    assert llm.openai_api_base == "https://openai-proxy.example/v1"


def test_factory_requires_provider_credential(monkeypatch, manager):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ValidateErrorException) as error:
        manager.create_chat_model(
            {"provider": "deepseek", "model": "deepseek-v4-flash"}
        )

    assert "DEEPSEEK_API_KEY" in error.value.message


@pytest.mark.parametrize(
    "model_config",
    [
        {"provider": "missing", "model": "model"},
        {"provider": "openai", "model": "missing"},
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "parameters": {"base_url": "https://example.com"},
        },
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "parameters": {"temperature": "hot"},
        },
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "parameters": {"temperature": 3},
        },
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "parameters": {"unknown": True},
        },
        {
            "provider": "moonshot",
            "model": "kimi-k3",
            "parameters": {"temperature": 0},
        },
    ],
)
def test_invalid_model_configs_are_rejected(manager, model_config):
    with pytest.raises(ValidateErrorException):
        manager.validate_model_config(model_config)


def test_legacy_max_tokens_parameter_is_accepted_and_defaults_are_applied(manager):
    config = manager.validate_model_config(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "parameters": {"max_tokens": 1024},
        }
    )

    assert config.parameters["max_tokens"] == 1024
    assert "max_completion_tokens" not in config.parameters
    assert config.parameters["temperature"] == 1


def test_system_model_uses_environment_selection(monkeypatch, manager):
    monkeypatch.setenv("SYSTEM_LLM_PROVIDER", "zhipu")
    monkeypatch.setenv("SYSTEM_LLM_MODEL", "glm-5.2")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")

    llm = manager.create_system_chat_model({"temperature": 0})

    assert llm.model_name == "glm-5.2"
    assert llm.temperature == 0


def test_structured_output_catalog_uses_provider_specific_strategies(manager):
    assert {
        provider_name: (
            manager.get_provider(
                provider_name
            ).provider_entity.structured_output_strategy.value,
            manager.get_provider(
                provider_name
            ).provider_entity.structured_output_strict,
        )
        for provider_name in STRUCTURED_OUTPUT_STRATEGIES
    } == STRUCTURED_OUTPUT_STRATEGIES


@pytest.mark.parametrize(
    ("provider_name", "expected_method", "expected_strict"),
    [
        (provider_name, *strategy)
        for provider_name, strategy in STRUCTURED_OUTPUT_STRATEGIES.items()
    ],
)
def test_structured_factory_applies_declared_strategy(
    monkeypatch,
    manager,
    provider_name,
    expected_method,
    expected_strict,
):
    captured = {}

    class FakeChatModel:
        def with_structured_output(self, schema, **kwargs):
            captured.update(schema=schema, kwargs=kwargs)
            return RunnableLambda(
                lambda _input: SuggestedQuestions(questions=[])
            )

    monkeypatch.setattr(
        LanguageModelManager,
        "create_chat_model",
        lambda _self, _config: FakeChatModel(),
    )

    structured_model = manager.create_structured_chat_model(
        {
            "provider": provider_name,
            "model": VISIBLE_MODELS[provider_name][0],
        },
        SuggestedQuestions,
    )

    assert structured_model.invoke("history").questions == []
    assert captured["schema"] is SuggestedQuestions
    assert captured["kwargs"]["method"] == expected_method
    if expected_method == "json_schema":
        assert captured["kwargs"]["strict"] is expected_strict
    else:
        assert "strict" not in captured["kwargs"]


def test_structured_factory_retries_schema_validation_once(
    monkeypatch, manager
):
    attempts = 0

    class FakeChatModel:
        def with_structured_output(self, _schema, **_kwargs):
            def invoke(_input):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    return None
                return {"questions": ["下一步是什么？"]}

            return RunnableLambda(invoke)

    monkeypatch.setattr(
        LanguageModelManager,
        "create_chat_model",
        lambda _self, _config: FakeChatModel(),
    )

    structured_model = manager.create_structured_chat_model(
        {"provider": "zhipu", "model": "glm-5.2"},
        SuggestedQuestions,
        max_attempts=2,
    )

    result = structured_model.invoke("history")

    assert attempts == 2
    assert result.questions == ["下一步是什么？"]


def test_provider_sdks_are_confined_to_language_model_core():
    internal_path = Path(__file__).parents[4] / "internal"
    provider_path = internal_path / "core" / "language_model" / "providers"
    forbidden_imports = (
        "langchain_openai",
        "langchain_deepseek",
        "langchain_ollama",
    )

    offenders = []
    for python_file in internal_path.rglob("*.py"):
        if provider_path in python_file.parents:
            continue
        source = python_file.read_text(encoding="utf-8")
        if any(module in source for module in forbidden_imports):
            offenders.append(str(python_file.relative_to(internal_path)))

    assert offenders == []
