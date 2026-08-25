from internal.core.language_model import LanguageModelManager
from internal.service.language_model_service import LanguageModelService


def test_language_model_list_only_exposes_visible_catalog():
    service = LanguageModelService(
        db=None,
        language_model_manager=LanguageModelManager(),
    )

    providers = service.get_language_models()

    assert [provider["name"] for provider in providers] == [
        "openai",
        "deepseek",
        "moonshot",
        "doubao",
        "zhipu",
    ]
    assert [model["model_name"] for model in providers[2]["models"]] == [
        "kimi-k3",
        "kimi-k2.6",
    ]
    assert all(
        "visible" not in model
        for provider in providers
        for model in provider["models"]
    )


def test_language_model_detail_does_not_expose_runtime_visibility():
    service = LanguageModelService(
        db=None,
        language_model_manager=LanguageModelManager(),
    )

    model = service.get_language_model("moonshot", "moonshot-v1-8k")

    assert model["model_name"] == "moonshot-v1-8k"
    assert "visible" not in model
