from types import SimpleNamespace
from uuid import uuid4

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
        def create_chat_model(self, model_config):
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
