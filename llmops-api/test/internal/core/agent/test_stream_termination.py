from concurrent.futures import ThreadPoolExecutor
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import HumanMessage
from openai import BadRequestError

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.agents.function_call_agent import FunctionCallAgent
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent
from internal.entity.conversation_entity import InvokeFrom


@pytest.fixture
def manager():
    # 不初始化 Flask Injector，不连接 Redis 或加载 .env。
    manager = AgentQueueManager.__new__(AgentQueueManager)
    manager.user_id = uuid4()
    manager.invoke_from = InvokeFrom.SERVICE_API
    manager.redis_client = SimpleNamespace(setex=Mock(), get=Mock(return_value=None))
    manager._queues = {}
    manager._lock = RLock()
    manager._closed_tasks = set()
    return manager


def test_concurrent_first_access_uses_one_queue(manager):
    entered, release, second_started = Event(), Event(), Event()

    def setex(*args):
        entered.set()
        assert release.wait(2)

    manager.redis_client.setex.side_effect = setex
    task_id = uuid4()

    def second_access():
        second_started.set()
        return manager.queue(task_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(manager.queue, task_id)
        assert entered.wait(2)
        second = pool.submit(second_access)
        assert second_started.wait(2)
        release.set()
        assert first.result(timeout=2) is second.result(timeout=2)
    manager.redis_client.setex.assert_called_once()


@pytest.mark.parametrize("event", [QueueEvent.ERROR, QueueEvent.AGENT_END,
                                   QueueEvent.STOP, QueueEvent.TIMEOUT])
def test_terminal_event_ends_without_redis_or_later_frames(manager, event):
    task_id = uuid4()
    manager.publish(task_id, AgentThought(id=uuid4(), task_id=task_id, event=event))
    manager.publish_error(task_id, "duplicate")
    manager.publish(task_id, AgentThought(id=uuid4(), task_id=task_id,
                                         event=QueueEvent.AGENT_MESSAGE, answer="late"))
    manager.redis_client.get.side_effect = AssertionError("Redis checked after terminal event")

    assert [item.event for item in manager.listen(task_id)] == [event]
    manager.redis_client.get.assert_not_called()
    assert manager.queue(task_id).get_nowait() is None
    assert manager.queue(task_id).empty()


@pytest.mark.parametrize("cause,expected", [("stop", QueueEvent.STOP),
                                            ("timeout", QueueEvent.TIMEOUT)])
def test_listener_generated_terminal_event(manager, monkeypatch, cause, expected):
    task_id = uuid4()
    manager.publish(task_id, AgentThought(id=uuid4(), task_id=task_id, event=QueueEvent.PING))
    clock = iter([0, 601 if cause == "timeout" else 1])
    monkeypatch.setattr("internal.core.agent.agents.agent_queue_manager.time.monotonic",
                        lambda: next(clock))
    manager.redis_client.get.return_value = b"1" if cause == "stop" else None
    assert [item.event for item in manager.listen(task_id)] == [QueueEvent.PING, expected]


@pytest.mark.parametrize("failure", ["provider", "unhandled"])
@pytest.mark.parametrize("streaming", [True, False])
def test_background_failure_finishes_agent_response(manager, failure, streaming):
    def model_stream(messages):
        response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid"))
        raise BadRequestError("Prompt exceeds max length", response=response,
                              body={"code": "1261", "message": "Prompt exceeds max length"})

    llm = SimpleNamespace(stream=model_stream, features=[], metadata={})
    agent = FunctionCallAgent.model_construct(llm=llm, agent_config=AgentConfig(user_id=uuid4()))
    agent._agent_queue_manager = manager
    if failure == "provider":
        agent._agent = agent._build_agent()
    else:
        def invoke(state):
            raise RuntimeError("unexpected node failure")
        agent._agent = SimpleNamespace(invoke=invoke)
    state = {"messages": [HumanMessage("hello")], "long_term_memory": ""}

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: list(agent.stream(state)) if streaming else agent.invoke(state))
        try:
            result = future.result(timeout=3)
        finally:
            # 防止回归失败时测试自身一直等待消费者。
            if not future.done():
                manager.stop_listen(state["task_id"])

    if streaming:
        errors = [item for item in result if item.event == QueueEvent.ERROR]
        assert len(errors) == 1
        assert result[-1].event == QueueEvent.ERROR
        message = errors[0].observation
    else:
        assert result.status == QueueEvent.ERROR
        message = result.error
    assert ("Prompt exceeds max length" if failure == "provider" else "unexpected node failure") in message
