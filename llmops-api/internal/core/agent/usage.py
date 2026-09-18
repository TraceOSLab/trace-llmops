"""Agent 事件合并及用量汇总，供流式、非流式和持久化共用。"""

from decimal import Decimal

from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent


USAGE_FIELDS = {
    "message_token_count", "answer_token_count", "total_token_count",
    "message_unit_price", "answer_unit_price", "message_price_unit",
    "answer_price_unit", "total_price", "usage",
}
STREAM_FIELDS = {
    "event", "thought", "observation", "tool", "tool_input", "answer", "latency",
    *USAGE_FIELDS,
}


def merge_agent_thought(events: dict[str, AgentThought], incoming: AgentThought) -> None:
    if incoming.event == QueueEvent.PING:
        return
    key = str(incoming.id)
    previous = events.get(key)
    if incoming.event != QueueEvent.AGENT_MESSAGE or previous is None:
        events[key] = incoming
        return
    updates = {
        "thought": previous.thought + incoming.thought,
        "answer": previous.answer + incoming.answer,
        "latency": incoming.latency,
    }
    # 结算事件携带整次调用用量，覆盖而非相加；重复结算不会重复计费。
    if incoming.usage is not None:
        updates.update(incoming.model_dump(include=USAGE_FIELDS))
        updates["usage"] = incoming.usage
    events[key] = previous.model_copy(update=updates)


def summarize_usage(events: list[AgentThought]) -> dict:
    unique = {str(event.id): event for event in events}
    calls = [event for event in unique.values() if event.event in {
        QueueEvent.AGENT_MESSAGE, QueueEvent.AGENT_THOUGHT
    } and (event.usage is None or event.usage.source != "not_called")]
    interrupted = any(event.event in {QueueEvent.STOP, QueueEvent.TIMEOUT, QueueEvent.ERROR}
                      for event in unique.values())
    usages = [event.usage for event in calls if event.usage is not None]
    complete = not interrupted and all(event.usage and event.usage.complete for event in calls)
    currencies = {u.currency for u in usages if u.currency}
    known_costs: dict[str, Decimal] = {}
    for usage in usages:
        if usage.total_price is not None and usage.currency:
            known_costs[usage.currency] = known_costs.get(usage.currency, Decimal("0")) + usage.total_price
    price_complete = complete and all(u.total_price is not None for u in usages)
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    cost = (known_costs.get(currency, Decimal("0"))
            if price_complete and len(currencies) <= 1 else None)
    return {
        "scope": "agent", "call_count": len(calls), "complete": bool(complete),
        "input_tokens": sum(u.input_tokens or 0 for u in usages),
        "output_tokens": sum(u.output_tokens or 0 for u in usages),
        "total_tokens": sum(u.total_tokens or 0 for u in usages),
        "currency": currency, "total_price": str(cost) if cost is not None else None,
        "price_status": "calculated" if cost is not None else "incomplete",
        "known_costs": {key: str(value) for key, value in known_costs.items()},
    }


def summary_fields(summary: dict) -> dict:
    return {
        "message_token_count": summary["input_tokens"],
        "answer_token_count": summary["output_tokens"],
        "total_token_count": summary["total_tokens"],
        "total_price": Decimal(summary["total_price"] or
                               summary["known_costs"].get(summary["currency"], "0")),
        "usage": summary,
    }


def thought_usage_fields(event: AgentThought) -> dict:
    values = event.model_dump(include=USAGE_FIELDS - {"usage"})
    values["usage"] = event.usage.model_dump(mode="json") if event.usage else {}
    return values


def stream_payload(event: AgentThought, events: dict[str, AgentThought]) -> dict:
    data = event.model_dump(mode="json", include=STREAM_FIELDS)
    data["total_price"] = (str(event.usage.total_price)
                           if event.usage and event.usage.total_price is not None else None)
    if event.event in {QueueEvent.AGENT_END, QueueEvent.STOP, QueueEvent.TIMEOUT, QueueEvent.ERROR}:
        summary = summarize_usage(list(events.values()))
        data.update({
            "usage": summary, "message_token_count": summary["input_tokens"],
            "answer_token_count": summary["output_tokens"],
            "total_token_count": summary["total_tokens"],
            "total_price": summary["total_price"],
        })
    return data
