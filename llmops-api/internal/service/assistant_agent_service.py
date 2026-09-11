from dataclasses import dataclass
from datetime import datetime
from gc import enable
import json
from threading import Thread
from uuid import UUID

from flask import current_app
from injector import inject
from langchain_classic.tools import BaseTool
from langchain_community.tools import tool
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import desc

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.agents.function_call_agent import FunctionCallAgent
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.entities.queue_entity import QueueEvent
from internal.core.language_model.language_model_manager import LanguageModelManager
from internal.core.memory.token_buffer_memory import TokenBufferMemory
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.model.account import Account
from internal.model.conversation import Message
from internal.schema.assistant_agent_schema import GetAssistantAgentMessagesWithPageReq
from internal.service.base_service import BaseService
from internal.service.conversation_service import ConversationService
from internal.task.app_task import auto_create_app
from pkg.paginator.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class AssistantAgentService(BaseService):
    """辅助AGENT服务"""

    db: SQLAlchemy
    language_model_manager: LanguageModelManager
    conversation_service: ConversationService

    def assistant_agent_chat(self, query, account_id: UUID):
        """辅助智能体对话"""

        account = self.get(Account, account_id)
        assistant_agent_id = current_app.config.get("ASSISTANT_AGENT_ID")

        # 当前辅助智能体会话信息
        conversation = account.assistant_agent_conversation

        # 创建辅助智能体消息
        message = self.create(
            Message,
            app_id=assistant_agent_id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.ASSISTANT_AGENT,
            created_by=account.id,
            query=query,
            status=MessageStatus.NORMAL,
        )

        # 使用系统默认模型作为LLM
        llm = self.language_model_manager.create_system_chat_model({"temperature": 0.7})

        # 提取记忆
        token_buffer_memory = TokenBufferMemory(
            db=self.db,
            conversation=conversation,
            model_instance=llm,
        )
        history = token_buffer_memory.get_history_prompt_messages(message_limit=3)

        # 将草稿配置中的tools转换成LangChain工具
        tools = [
            # self.faiss_service.convert_faiss_to_tool(),
            self.convert_create_app_to_tool(account.id),
        ]

        # 构建智能体
        agent = FunctionCallAgent(
            llm=llm,
            agent_config=AgentConfig(
                user_id=account.id,
                invoke_from=InvokeFrom.ASSISTANT_AGENT,
                enable_long_term_memory=True,
                tools=tools,
            ),
        )

        # 提取 agent_thought
        agent_thoughts = {}
        for agent_thought in agent.stream(
            {
                "messages": [HumanMessage(query)],
                "history": history,
                "long_term_memory": conversation.summary,
            }
        ):
            event_id = str(agent_thought.id)

            # 将数据填充到agent_thought
            if agent_thought.event != QueueEvent.PING:
                # 处理 agent_message 数据为叠加
                if agent_thought.event == QueueEvent.AGENT_MESSAGE:
                    if event_id not in agent_thoughts:
                        agent_thoughts[event_id] = agent_thought
                    else:
                        # 叠加智能体消息
                        agent_thoughts[event_id] = agent_thoughts[event_id].model_copy(
                            update={
                                "thought": agent_thoughts[event_id].thought
                                + agent_thought.thought,
                                "answer": agent_thoughts[event_id].answer
                                + agent_thought.answer,
                                "latency": agent_thought.latency,
                            }
                        )
                else:
                    # 处理其他类型事件的消息
                    agent_thoughts[event_id] = agent_thought
            data = {
                **agent_thought.model_dump(
                    include={
                        "event",
                        "thought",
                        "observation",
                        "tool",
                        "tool_input",
                        "answer",
                        "latency",
                    }
                ),
                "id": event_id,
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "task_id": str(agent_thought.task_id),
            }
            yield f"event: {agent_thought.event}\ndata:{json.dumps(data)}\n\n"

        thread = Thread(
            target=self.conversation_service.save_agent_thoughts,
            kwargs={
                "flask_app": current_app._get_current_object(),
                "account_id": account.id,
                "app_id": assistant_agent_id,
                "app_config": {
                    "long_term_memory": {"enable": True},
                },
                "conversation_id": conversation.id,
                "message_id": message.id,
                "agent_thoughts": [
                    agent_thought for agent_thought in agent_thoughts.values()
                ],
            },
        )
        thread.start()

    def stop_assistant_agent_chat(self, task_id: UUID, account: Account):
        """辅助智能体停止会话"""

        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.ASSISTANT_AGENT, account.id)

    def get_assistant_agent_messages_with_page(
        self, req: GetAssistantAgentMessagesWithPageReq, account: Account
    ) -> tuple[list[Message], Paginator]:
        """辅助智能体消息分页列表"""
        # 获取应用的调试会话
        conversation = account.assistant_agent_conversation

        # 构建分页器
        paginator = Paginator(db=self.db, req=req)
        filters = []
        if req.created_at.data:
            # 将时间戳转换成DateTime
            created_at_datetime = datetime.fromtimestamp(req.created_at.data)
            filters.append(Message.created_at <= created_at_datetime)

        messages = paginator.paginate(
            self.db.session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.status.in_([MessageStatus.STOP, MessageStatus.NORMAL]),
                Message.answer != "",
                *filters,
            )
            .order_by(desc("created_at"))
        )

        return messages, paginator

    def delete_assistant_agent_conversation(self, account: Account):
        """清空辅助Agent智能体会话消息列表"""
        self.update(account, assistant_agent_conversation_id=None)

    @classmethod
    def convert_create_app_to_tool(cls, account_id: UUID) -> BaseTool:
        """自动创建智能体应用的 langchain 工具"""

        class CreateAppInput(BaseModel):
            """创建应用的输入结构"""

            name: str = Field(
                description="需要创建的Agent/应用名称，长度不超过50个字符"
            )
            description: str = Field(
                description="需要创建的Agent/应用描述，请详细概括该应用的功能"
            )

        @tool("create_app", args_schema=CreateAppInput)
        def create_app(name: str, description: str) -> str:
            """如果用户提出了需要创建一个Agent/应用，你可以调用此工具，参数的输入是应用的名称+描述，返回的数据是创建后的成功提示"""

            auto_create_app.delay(name, description, account_id)

            return (
                f"已调用异步任务创建应用。\n应用名称: {name}\n应用描述: {description}"
            )

        return create_app
