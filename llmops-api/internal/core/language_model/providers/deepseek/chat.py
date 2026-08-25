from langchain_deepseek import ChatDeepSeek

from internal.core.language_model.entities.model_entity import BaseLanguageModel


class Chat(ChatDeepSeek, BaseLanguageModel):
    """DeepSeek 专属 LangChain 对话模型。"""

    pass
