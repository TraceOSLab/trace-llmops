from langchain_openai import ChatOpenAI

from internal.core.language_model.entities.model_entity import BaseLanguageModel
from internal.core.language_model.providers.usage import preserve_usage


class Chat(ChatOpenAI, BaseLanguageModel):
    """智谱 GLM OpenAI-compatible 对话模型。"""

    stream_usage: bool = True

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        return preserve_usage(generation, chunk)
