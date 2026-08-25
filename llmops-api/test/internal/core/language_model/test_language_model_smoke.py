"""显式启用的真实 Provider 冒烟测试；默认永远不会访问公网或付费模型。"""

import os

import pytest
from langchain_core.tools import tool

from internal.core.language_model import LanguageModelManager


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_SMOKE_TESTS", "").lower() != "true",
    reason="set RUN_LLM_SMOKE_TESTS=true to call paid provider APIs",
)


@tool
def add(left: int, right: int) -> int:
    """Add two integers."""
    return left + right


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("openai", "gpt-4o-mini"),
        ("deepseek", "deepseek-v4-flash"),
        ("moonshot", "kimi-k2.6"),
        ("doubao", "doubao-seed-2-0-lite-260215"),
        ("zhipu", "glm-4.5-flash"),
    ],
)
def test_provider_text_and_tool_call(provider, model):
    llm = LanguageModelManager().create_chat_model(
        {
            "provider": provider,
            "model": model,
            "parameters": {},
        }
    )

    text_response = llm.invoke("只回复 OK")
    assert text_response.content

    tool_response = llm.bind_tools([add]).invoke("使用工具计算 1 + 2")
    assert tool_response.content or tool_response.tool_calls
