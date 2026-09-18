from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from internal.core.language_model.usage import collect_usage
from internal.core.language_model.providers.deepseek.chat import Chat as DeepSeek
from internal.core.language_model.providers.doubao.chat import Chat as Doubao
from internal.core.language_model.providers.zhipu.chat import Chat as GLM


NOW = datetime(2026, 9, 18, 2, tzinfo=timezone.utc)  # 周五北京时间 10:00
PRICING = {"input": "2", "output": "8", "cache_read": "0.2", "unit": "0.000001"}


def message(input_tokens=1000, output_tokens=200, cache=800):
    return AIMessage(content="答案", usage_metadata={
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_token_details": {"cache_read": cache} if cache is not None else {},
        "output_token_details": {"reasoning": 100},
    })


def test_cache_and_reasoning_are_subsets_not_additional_tokens():
    result = collect_usage(message(), {"provider": "zhipu", "pricing": PRICING}, NOW)
    assert result.total_tokens == 1200
    assert result.reasoning_tokens == 100
    assert result.total_price == Decimal("0.00216")
    assert result.price_status == "calculated"
    assert result.pricing["unit"] == "0.000001"


@pytest.mark.parametrize("kind,status", [
    ("missing", "missing_usage"), ("no_price", "missing_pricing"),
    ("no_cache", "missing_cache_usage"), ("interrupted", "incomplete_usage"),
    ("invalid", "invalid_usage"),
])
def test_unknown_values_are_not_reported_as_free(kind, status):
    msg = None if kind == "missing" else message(cache=None if kind == "no_cache" else 800)
    if kind == "invalid":
        msg.usage_metadata["input_token_details"]["cache_read"] = 1001
    metadata = {} if kind == "no_price" else {"pricing": PRICING}
    result = collect_usage(msg, metadata, NOW, complete=kind != "interrupted")
    assert result.price_status == status
    assert result.total_price is None


def test_explicit_free_model_and_raw_usage_fallback():
    msg = AIMessage(content="", response_metadata={"token_usage": {
        "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
        "prompt_cache_hit_tokens": 80,
    }})
    result = collect_usage(msg, {"pricing": {"input": "0", "output": "0"}}, NOW)
    assert result.cache_read_tokens == 80
    assert result.total_price == Decimal("0")
    assert result.price_status == "calculated"


@pytest.mark.parametrize("hour,day,multiplier", [
    (0, 18, "0.5"), (1, 18, "1"), (4, 18, "0.5"),
    (6, 18, "1"), (10, 18, "0.5"), (2, 19, "0.5"),
])
def test_deepseek_time_bands(hour, day, multiplier):
    result = collect_usage(message(), {"pricing": {**PRICING, "schedule": "deepseek_peak"}},
                           datetime(2026, 9, day, hour, tzinfo=timezone.utc))
    assert result.total_price == Decimal("0.00216") * Decimal(multiplier)


def test_tier_boundaries_and_price_snapshot():
    pricing = {"tiers": [
        {"max_input_tokens": 32000, "input": "3.2", "output": "16", "cache_read": "0.64"},
        {"max_input_tokens": 128000, "input": "4.8", "output": "24", "cache_read": "0.96"},
    ]}
    low = collect_usage(message(input_tokens=32000), {"pricing": pricing}, NOW)
    high = collect_usage(message(input_tokens=32001), {"pricing": pricing}, NOW)
    unknown = collect_usage(message(input_tokens=128001), {"pricing": pricing}, NOW)
    assert low.pricing["input"] == "3.2"
    assert high.pricing["input"] == "4.8"
    assert unknown.price_status == "missing_pricing"
    pricing["tiers"][0]["input"] = "99"
    assert low.pricing["input"] == "3.2"


@pytest.mark.parametrize("cls,model", [(DeepSeek, "deepseek-v4-pro"), (GLM, "glm-5.2"),
                                      (Doubao, "doubao-seed-2-0-pro-260215")])
def test_real_sdk_stream_with_mock_http_preserves_usage(cls, model):
    """走真实 SDK 的 stream 和转换路径，HTTP 完全由 MockTransport 接管。"""
    import json
    captured = {}
    chunks = [
        {"id": "test", "model": model, "choices": [{"index": 0, "delta": {"content": "你好"}}]},
        {"id": "test", "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {"id": "test", "model": model, "choices": [], "usage": {
            "prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200,
            "prompt_cache_hit_tokens": 800,
        }},
    ]

    def handle(request):
        captured.update(json.loads(request.content))
        body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        llm = cls(model=model, api_key="test-key", base_url="https://mock.invalid/v1",
                  http_client=client, max_retries=0)
        responses = list(llm.stream("你好"))
    assert captured["stream_options"] == {"include_usage": True}
    final = next(chunk for chunk in reversed(responses) if chunk.usage_metadata)
    result = collect_usage(final, {"pricing": PRICING}, NOW)
    assert result.cache_read_tokens == 800
    assert result.total_price == Decimal("0.00216")


def test_missing_raw_fields_do_not_become_sdk_zero_usage():
    llm = DeepSeek.model_construct(model_name="deepseek-v4-pro")
    result = llm._convert_chunk_to_generation_chunk(
        {"choices": [], "usage": {"total_tokens": 12}}, AIMessageChunk, None
    )
    assert collect_usage(result.message, {"pricing": PRICING}, NOW).source == "missing"
