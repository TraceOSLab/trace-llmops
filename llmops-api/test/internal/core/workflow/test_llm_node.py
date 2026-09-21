from types import SimpleNamespace
from uuid import uuid4

import pytest

from internal.core.language_model import LanguageModelManager
from internal.exception import ValidateErrorException
from internal.core.workflow.entities.node_entity import NodeType
from internal.core.workflow.nodes.llm.llm_entity import LLMNodeData
from internal.core.workflow.nodes.llm.llm_node import LLMNode


def test_llm_node_uses_complete_provider_config(monkeypatch):
    expected_config = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "parameters": {"temperature": 0.5},
    }
    fake_llm = SimpleNamespace(
        stream=lambda prompt: iter(
            [SimpleNamespace(content="hello"), SimpleNamespace(content=" world")]
        )
    )
    captured = {}

    class FakeManager:
        def create_language_model(self, model_config):
            captured["model_config"] = model_config
            return fake_llm

    monkeypatch.setattr(
        "internal.core.workflow.nodes.llm.llm_node.get_language_model_manager",
        lambda: FakeManager(),
    )
    node = LLMNode(
        node_data=LLMNodeData(
            id=uuid4(),
            node_type=NodeType.LLM,
            title="answer",
            prompt="hello",
            model_config=expected_config,
        )
    )

    result = node.invoke({"inputs": {}, "node_results": []})

    assert captured["model_config"] == expected_config
    assert result["node_results"][0].outputs == {"output": "hello world"}


def test_missing_model_error_identifies_workflow_node_and_model(monkeypatch):
    manager = LanguageModelManager()
    monkeypatch.setattr(
        "internal.core.workflow.nodes.llm.llm_node.get_language_model_manager",
        lambda: manager,
    )
    node_id = uuid4()
    node = LLMNode(
        node_data=LLMNodeData(
            id=node_id,
            node_type=NodeType.LLM,
            title="answer",
            prompt="hello",
            model_config={"provider": "deepseek", "model": "missing-model"},
        )
    )

    with pytest.raises(ValidateErrorException) as error:
        node.invoke({"inputs": {}, "node_results": []})

    assert str(node_id) in error.value.message
    assert "answer" in error.value.message
    assert "deepseek" in error.value.message
    assert "missing-model" in error.value.message
    assert isinstance(error.value.__cause__, ValidateErrorException)


@pytest.mark.parametrize("config_key", ["model_config", "language_model_config"])
def test_glm_config_survives_node_serialization(config_key):
    config = {
        "provider": "zhipu",
        "model": "glm-4.5-flash",
        "parameters": {
            "frequency_penalty": 0.2,
            "max_tokens": 8192,
            "presence_penalty": 0.2,
            "temperature": 0.5,
            "top_p": 0.85,
        },
    }
    node = LLMNodeData(**{
        "id": uuid4(),
        "node_type": "llm",
        "title": "answer",
        "prompt": "hello",
        config_key: config,
    })
    restored = LLMNodeData.model_validate(node.model_dump(mode="json"))

    assert restored.language_model_config == config
    assert LanguageModelManager().validate_model_config(
        restored.language_model_config
    ).model_dump() == config
