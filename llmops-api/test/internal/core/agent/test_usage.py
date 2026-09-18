from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from internal.core.agent.agents.function_call_agent import FunctionCallAgent
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent
from internal.core.agent.usage import merge_agent_thought, summarize_usage, stream_payload
from internal.core.language_model.usage import TokenUsage


def run_node(chunks):
    events = []

    def stream(_messages):
        for chunk in chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    llm = SimpleNamespace(stream=stream, features=[], metadata={
        "provider": "zhipu", "model": "glm-5.2",
        "pricing": {"input": "2", "output": "8", "unit": "0.000001"},
    })
    agent = FunctionCallAgent.model_construct(llm=llm, agent_config=AgentConfig(user_id=uuid4()))
    queue = SimpleNamespace(publish=lambda _task, event: events.append(event),
                            publish_error=lambda task, error: events.append(AgentThought(
                                id=uuid4(), task_id=task, event=QueueEvent.ERROR, observation=error)))
    agent._agent_queue_manager = queue
    state = {"messages": [HumanMessage(content="你好")], "iteration_count": 0, "task_id": uuid4()}
    return agent, state, events


def usage_chunk(inp=100, out=20):
    return AIMessageChunk(content="", usage_metadata={
        "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out,
    })


def test_empty_final_chunk_settles_once_and_preserves_answer(monkeypatch):
    agent, state, events = run_node([
        AIMessageChunk(content="你"), usage_chunk(out=10), AIMessageChunk(content="好"), usage_chunk(),
    ])
    agent._llm_node(state)
    merged = {}
    for event in events:
        merge_agent_thought(merged, event)
    settlement = next(event for event in events if event.usage)
    merge_agent_thought(merged, settlement)  # 相同空结算事件重复到达
    answer = merged[str(settlement.id)]
    assert answer.answer == "你好"
    assert answer.answer_token_count == 20  # 不是累计快照相加的 30
    assert answer.total_price == Decimal("0.00036")
    summary = summarize_usage(list(merged.values()))
    assert summary["call_count"] == 1
    assert summary["total_tokens"] == 120
    assert stream_payload(events[-1], merged)["usage"] == summary
    # 块输出复用同一聚合路径。
    monkeypatch.setattr(FunctionCallAgent, "stream", lambda *_args, **_kwargs: iter(events))
    result = agent.invoke(state)
    assert result.answer == "你好"
    assert result.total_token_count == 120
    assert result.total_price == Decimal("0.00036")


def test_tool_call_round_and_final_answer_are_both_counted():
    tool_chunk = AIMessageChunk(content="", tool_call_chunks=[{
        "name": "search", "args": '{"query":"test"}', "id": "tool-1", "index": 0,
    }])
    agent, state, events = run_node([tool_chunk, usage_chunk()])
    agent._llm_node(state)
    assert events[0].event == QueueEvent.AGENT_THOUGHT
    agent2, state2, events2 = run_node([AIMessageChunk(content="答案"), usage_chunk(200, 30)])
    agent2._llm_node(state2)
    merged = {}
    for event in [*events, *events2]:
        merge_agent_thought(merged, event)
    summary = summarize_usage(list(merged.values()))
    assert summary["input_tokens"] == 300
    assert summary["output_tokens"] == 50
    assert summary["total_tokens"] == 350
    assert Decimal(summary["total_price"]) == Decimal("0.001")


def test_stream_failure_keeps_partial_answer_and_unknown_cost():
    agent, state, events = run_node([AIMessageChunk(content="部分答案"), RuntimeError("broken stream")])
    with pytest.raises(RuntimeError):
        agent._llm_node(state)
    merged = {}
    for event in events:
        merge_agent_thought(merged, event)
    assert next(iter(merged.values())).answer == "部分答案"
    summary = summarize_usage(list(merged.values()))
    assert summary["complete"] is False
    assert summary["total_price"] is None
    assert events[-1].event == QueueEvent.ERROR


def test_non_model_responses_are_zero_cost_not_missing_usage():
    thought = AgentThought(id=uuid4(), task_id=uuid4(), event=QueueEvent.AGENT_MESSAGE,
                           answer="审核拒绝", usage=TokenUsage.not_called())
    summary = summarize_usage([thought])
    assert summary["call_count"] == 0
    assert summary["complete"] is True
    assert Decimal(summary["total_price"]) == 0


def test_mixed_currencies_and_stop_do_not_claim_complete_total():
    events = [AgentThought(
        id=uuid4(), task_id=uuid4(), event=QueueEvent.AGENT_THOUGHT,
        usage=TokenUsage(source="provider", complete=True, input_tokens=1, output_tokens=1,
                         total_tokens=2, currency=currency, total_price=Decimal("1")),
    ) for currency in ["CNY", "USD"]]
    summary = summarize_usage(events)
    assert summary["total_price"] is None
    assert summary["known_costs"] == {"CNY": "1", "USD": "1"}
    events.append(AgentThought(id=uuid4(), task_id=uuid4(), event=QueueEvent.STOP))
    assert summarize_usage(events)["complete"] is False
