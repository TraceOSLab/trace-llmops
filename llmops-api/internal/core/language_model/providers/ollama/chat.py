from typing import Any

from langchain_ollama import ChatOllama

from internal.core.language_model.entities.model_entity import BaseLanguageModel


class Chat(ChatOllama, BaseLanguageModel):
    """Ollama 模型"""

    def __init__(self, **kwargs: Any) -> None:
        """将项目统一的输出长度参数转换为 Ollama 参数。"""
        max_tokens = kwargs.pop("max_tokens", None)
        if max_tokens is not None and "num_predict" not in kwargs:
            kwargs["num_predict"] = max_tokens
        super().__init__(**kwargs)
