"""供应商用量归一化与单次调用计价；不通过重新分词推算账单。"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, ValidationError


class TokenUsage(BaseModel):
    provider: str = ""
    model: str = ""
    response_model: str = ""
    source: Literal["provider", "missing", "not_called"] = "missing"
    complete: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    currency: str | None = None
    total_price: Decimal | None = None
    price_status: str = "missing_usage"
    pricing: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""

    @classmethod
    def not_called(cls) -> "TokenUsage":
        return cls(source="not_called", complete=True, input_tokens=0,
                   output_tokens=0, total_tokens=0, total_price=Decimal("0"),
                   price_status="not_applicable")

    def legacy_fields(self) -> dict[str, Any]:
        """旧数值列是已知小计；是否完整以 usage 字段为准。unit 是乘数。"""
        return {
            "message_token_count": self.input_tokens or 0,
            "answer_token_count": self.output_tokens or 0,
            "total_token_count": self.total_tokens or 0,
            "message_unit_price": Decimal(str(self.pricing.get("input", "0"))),
            "answer_unit_price": Decimal(str(self.pricing.get("output", "0"))),
            "message_price_unit": Decimal(str(self.pricing.get("unit", "0"))),
            "answer_price_unit": Decimal(str(self.pricing.get("unit", "0"))),
            "total_price": self.total_price or Decimal("0"),
        }


class PriceTier(BaseModel):
    input: Decimal = Field(ge=0, allow_inf_nan=False)
    output: Decimal = Field(ge=0, allow_inf_nan=False)
    cache_read: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_input_tokens: int | None = Field(default=None, ge=0)


class ModelPricing(BaseModel):
    """unit 沿用乘数语义：每百万 token 的单价乘 0.000001。"""

    currency: Literal["CNY", "USD", "RMB"] = "CNY"
    unit: Decimal = Field(default=Decimal("0.000001"), gt=0, allow_inf_nan=False)
    input: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    output: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    cache_read: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    tiers: list[PriceTier] = Field(default_factory=list)
    schedule: Literal["flat", "deepseek_peak"] = "flat"
    source: str = ""
    checked_at: str = ""

    def rates(self, input_tokens: int, started_at: datetime) -> dict[str, Any] | None:
        if self.tiers:
            tier = next((t for t in self.tiers if t.max_input_tokens is None
                         or input_tokens <= t.max_input_tokens), None)
            if tier is None:
                return None
        elif self.input is not None and self.output is not None:
            tier = PriceTier(input=self.input, output=self.output, cache_read=self.cache_read)
        else:
            return None
        multiplier = Decimal("1")
        if self.schedule == "deepseek_peak":
            local = started_at.astimezone(ZoneInfo("Asia/Shanghai"))
            peak = local.weekday() < 5 and (9 <= local.hour < 12 or 14 <= local.hour < 18)
            multiplier = Decimal("1") if peak else Decimal("0.5")
        return {
            "input": str(tier.input * multiplier),
            "output": str(tier.output * multiplier),
            "cache_read": str(tier.cache_read * multiplier) if tier.cache_read is not None else None,
            "unit": str(self.unit),
            "currency": "CNY" if self.currency == "RMB" else self.currency,
            "source": self.source, "checked_at": self.checked_at,
            "schedule": self.schedule, "multiplier": str(multiplier),
            "max_input_tokens": tier.max_input_tokens,
        }


def collect_usage(
    message: BaseMessage | None, metadata: dict[str, Any],
    started_at: datetime | None = None, *, complete: bool = True,
) -> TokenUsage:
    """缺失、无效和中断数据均保留状态，不让统计失败中断回答保存。"""
    started_at = started_at or datetime.now(timezone.utc)
    response = getattr(message, "response_metadata", {}) or {}
    raw = response.get("token_usage") or {}
    standardized = getattr(message, "usage_metadata", None) or {}
    usage = TokenUsage(
        provider=metadata.get("provider", ""), model=metadata.get("model", ""),
        response_model=response.get("model_name") or response.get("model", ""),
        started_at=started_at.isoformat(),
    )
    input_tokens = standardized.get("input_tokens", raw.get("prompt_tokens"))
    output_tokens = standardized.get("output_tokens", raw.get("completion_tokens"))
    # 不能用 SDK 补出的零，掩盖原始响应明确缺少的字段。
    if raw and (raw.get("prompt_tokens") is None or raw.get("completion_tokens") is None):
        return usage
    if input_tokens is None or output_tokens is None:
        return usage
    cache = (standardized.get("input_token_details") or {}).get("cache_read")
    if cache is None:
        cache = (raw.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cache is None:
        cache = raw.get("prompt_cache_hit_tokens", raw.get("cached_tokens"))
    reasoning = (standardized.get("output_token_details") or {}).get("reasoning")
    if reasoning is None:
        reasoning = (raw.get("completion_tokens_details") or {}).get("reasoning_tokens")
    try:
        usage = TokenUsage(**{
            **usage.model_dump(), "source": "provider", "complete": complete,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": standardized.get("total_tokens", raw.get("total_tokens"))
                            if standardized.get("total_tokens", raw.get("total_tokens")) is not None
                            else input_tokens + output_tokens,
            "cache_read_tokens": cache, "reasoning_tokens": reasoning,
        })
    except (ValidationError, TypeError):
        return usage
    if (usage.total_tokens != usage.input_tokens + usage.output_tokens
            or (cache is not None and usage.cache_read_tokens > usage.input_tokens)
            or (reasoning is not None and usage.reasoning_tokens > usage.output_tokens)):
        usage.complete = False
        usage.price_status = "invalid_usage"
        return usage
    if not complete:
        usage.price_status = "incomplete_usage"
        return usage
    try:
        pricing = ModelPricing.model_validate(metadata.get("pricing") or {})
        rates = pricing.rates(usage.input_tokens, started_at)
    except (ValidationError, ValueError):
        rates = None
    if rates is None:
        usage.price_status = "missing_pricing"
        return usage
    usage.pricing = rates
    usage.currency = rates["currency"]
    input_rate = Decimal(rates["input"])
    output_rate = Decimal(rates["output"])
    cache_rate = Decimal(rates["cache_read"]) if rates["cache_read"] is not None else input_rate
    if cache_rate != input_rate and usage.cache_read_tokens is None and usage.input_tokens:
        usage.price_status = "missing_cache_usage"
        return usage
    cached = usage.cache_read_tokens or 0
    usage.total_price = (
        (usage.input_tokens - cached) * input_rate + cached * cache_rate
        + usage.output_tokens * output_rate
    ) * Decimal(rates["unit"])
    usage.price_status = "calculated"
    return usage
