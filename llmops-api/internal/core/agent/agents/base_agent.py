#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   base_agent
@Time   :   2026/1/23 09:00
@Author :   s.qiu@foxmail.com
"""

import uuid
from abc import abstractmethod
from threading import Thread
from typing import Optional, Iterator, Any

from langchain_core.load import Serializable
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pydantic import PrivateAttr

from internal.core.language_model.entities.model_entity import BaseLanguageModel
from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.entities.agent_entity import AgentState
from internal.core.agent.entities import AgentConfig
from internal.core.agent.entities.queue_entity import (
    AgentThought,
    AgentResult,
    QueueEvent,
)
from internal.core.agent.usage import merge_agent_thought, summarize_usage, summary_fields
from internal.exception import FailException



class BaseAgent(Serializable, Runnable):
    """基于Runnable 智能体基础类"""

    llm: BaseLanguageModel
    agent_config: AgentConfig
    _agent: CompiledStateGraph = PrivateAttr(None)
    _agent_queue_manager: AgentQueueManager = PrivateAttr(None)

    class Config:
        # 字段允许接收任意类型，且不需要校验器
        arbitrary_types_allowed = True

    def __init__(
        self, llm: BaseLanguageModel, agent_config: AgentConfig, *args, **kwargs
    ):
        """初始化智能体图程序"""
        super().__init__(*args, llm=llm, agent_config=agent_config, **kwargs)
        self._agent = self._build_agent()
        self._agent_queue_manager = AgentQueueManager(
            user_id=agent_config.user_id, invoke_from=agent_config.invoke_from
        )

    @abstractmethod
    def _build_agent(self) -> CompiledStateGraph:
        """构建智能体 等待子类实现"""
        raise NotImplementedError("_build_agent 未实现")

    def invoke(
        self, input: AgentState, config: Optional[RunnableConfig] = None, **kwargs: Any
    ) -> AgentResult:
        """块内容响应 一次生成后返回"""
        # 调用 stream 获取流事件输出数据
        agent_result = AgentResult(query=input["messages"][0].content)
        agent_thoughts = {}
        for agent_thought in self.stream(input, config):
            merge_agent_thought(agent_thoughts, agent_thought)
            if agent_thought.event == QueueEvent.AGENT_MESSAGE:
                agent_result.answer += agent_thought.answer
            if agent_thought.event in {QueueEvent.STOP, QueueEvent.TIMEOUT, QueueEvent.ERROR}:
                agent_result.status = agent_thought.event
                agent_result.error = agent_thought.observation if agent_thought.event == QueueEvent.ERROR else ""

        # 合并推理
        agent_result.agent_thoughts = [
            agent_thought for agent_thought in agent_thoughts.values()
        ]
        # 合并消息
        agent_result.message = next(
            (
                agent_thought.message
                for agent_thought in agent_thoughts.values()
                if agent_thought.event == QueueEvent.AGENT_MESSAGE
            ),
            [],
        )
        # 合并总耗时
        agent_result.latency = sum(
            [agent_thought.latency for agent_thought in agent_thoughts.values()]
        )

        return agent_result.model_copy(update=summary_fields(
            summarize_usage(agent_result.agent_thoughts)
        ))

    def stream(
        self,
        input: AgentState,
        config: Optional[RunnableConfig] = None,
        **kwargs: Optional[Any]
    ) -> Iterator[AgentThought]:
        """流式响应 每个Node 节点或者 每段Token 返回"""
        if not self._agent:
            raise FailException("智能体未构建！")
        input["task_id"] = input.get("task_id", uuid.uuid4())
        input["history"] = input.get("history", [])
        input["iteration_count"] = input.get("iteration_count", 0)

        # 创建子线程执行
        thread = Thread(target=self._agent.invoke, args=(input,))
        thread.start()

        yield from self._agent_queue_manager.listen(input["task_id"])

    @property
    def agent_queue_manager(self) -> AgentQueueManager:
        """只读属性 智能体队列管理器"""
        return self._agent_queue_manager
