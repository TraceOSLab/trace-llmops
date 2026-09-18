"""保留兼容接口的用量字段，避免 SDK 标准化时丢失缓存统计。"""

from copy import deepcopy


def preserve_usage(generation, chunk):
    if generation is not None and isinstance(chunk.get("usage"), dict):
        allowed = {
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_tokens_details", "completion_tokens_details",
            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "cached_tokens",
        }
        generation.message.response_metadata["token_usage"] = {
            key: deepcopy(value) for key, value in chunk["usage"].items() if key in allowed
        }
    return generation
