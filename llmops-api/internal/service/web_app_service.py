from dataclasses import dataclass
import json
from threading import Thread
from typing import Generator

from flask import current_app
from injector import inject
from langchain.messages import HumanMessage
from sqlalchemy import desc
from werkzeug.exceptions import FailedDependency

from internal.core.agent.agents.agent_queue_manager import AgentQueueManager
from internal.core.agent.agents.function_call_agent import FunctionCallAgent
from internal.core.agent.entities.agent_entity import AgentConfig
from internal.core.agent.usage import merge_agent_thought, stream_payload
from internal.core.memory.token_buffer_memory import TokenBufferMemory
from internal.entity.app_entity import AppStatus
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.entity.dataset_entity import RetrievalSource
from internal.exception.exception import FailException, ForbiddenException
from internal.model import conversation
from internal.model.account import Account
from internal.model.app import App
from internal.model.conversation import Conversation, Message
from internal.schema.web_app_schema import WebAppChatReq
from .app_config_service import AppConfigService

from .base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class WebAppService(BaseService):
    """Webapp 服务"""

    db: SQLAlchemy
    app_config_service: AppConfigService

    def get_web_app(self, token: str) -> App:
        """根据TOKEN获取应用"""
        app = self.db.session.query(App).filter(App.token == token).one_or_none()
        if not app:
            raise FailException("该应用不存在")
        if app.status != AppStatus.PUBLISHED:
            raise FailedDependency("该应用未发布")

        return app

    def web_app_chat(
        self, token: str, req: WebAppChatReq, account: Account
    ) -> Generator:
        """WEBAPP 会话"""
        app = self.get_web_app(token)

        # 校验会话归属信息
        if req.conversation_id.data:
            conversation = self.get(conversation.Conversation, req.conversation_id.data)
            if (
                not conversation
                or conversation.app_id != app.id
                or conversation.invoke_from != InvokeFrom.WEB_APP
                or conversation.created_by != account.id
                or conversation.is_deleted is True
            ):
                raise ForbiddenException("该会话不存在或者不属于当前应用/用户/调用方式")
        else:
            # 如果没有传递会话ID则新建会话
            conversation = self.create(
                Conversation,
                **{
                    "appid": app.id,
                    "name": "New Converstation",
                    "invoke_from": InvokeFrom.WEB_APP,
                    "created_by": account.id,
                },
            )

        # 获取当前应用 最新草稿配置
        app_config = self.app_config_service.get_app_config(app.id, account)

        # 获取当前应用 会话信息
        conversation = app.conversation

        # 新建消息记录
        message = self.create(
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.WEB_APP,
            created_by=account.id,
            query=req.query.data,
            status=MessageStatus.NORMAL,
        )

        # 根据配置实例化模型
        llm = self.language_model_manager.create_language_model(
            app_config["model_config"]
        )

        # 提取短期记忆
        token_buffer_memory = TokenBufferMemory(
            db=self.db, conversation=conversation, model_instance=llm
        )
        history = token_buffer_memory.get_history_prompt_messages(
            message_limit=app_config["dialog_round"]
        )

        tools = self.app_config_service.get_langchain_tools_by_tools_config(
            app_config["tools"]
        )

        # 关联知识库 构建 LangChain 知识库检索工具
        if app_config["datasets"]:
            dataset_retrieval = (
                self.retrieval_service.create_langchain_tool_from_search(
                    flask_app=current_app._get_current_object(),
                    dataset_ids=[dataset["id"] for dataset in app_config["datasets"]],
                    account_id=account.id,
                    retrival_source=RetrievalSource.APP,
                    **app_config["retrieval_config"],
                )
            )
            tools.append(dataset_retrieval)

        # 检测是否关联工作流，如果关联了工作流则将工作流构建成工具添加到tools中
        if app_config["workflows"]:
            workflow_tools = (
                self.app_config_service.get_langchain_tools_by_workflow_ids(
                    [workflow["id"] for workflow in app_config["workflows"]]
                )
            )
            tools.extend(workflow_tools)

        # 构建 AGENT 智能体 使用 FUNCTIONCALLAGENT
        agent = FunctionCallAgent(
            llm=llm,
            agent_config=AgentConfig(
                user_id=account.id,
                invoke_from=InvokeFrom.WEB_APP,
                enable_long_term_memory=app_config["long_term_memory"]["enable"],
                preset_prompt=app_config["preset_prompt"],
                review_config=app_config["review_config"],
                tools=tools,
            ),
        )

        # 执行智能体。客户端断开时，后台 Agent 仍可能继续产生终止事件；
        # 保留同一个 iterator 供后台排空，避免已创建的消息永久没有答案或终止状态。
        agent_thoughts = {}
        agent_stream = agent.stream(
            {
                "messages": [HumanMessage(req.query.data)],
                "history": history,
                "long_term_memory": conversation.summary,
            }
        )
        flask_app = current_app._get_current_object()

        def save_agent_thoughts() -> None:
            Thread(
                target=self.conversation_service.save_agent_thoughts,
                kwargs={
                    "flask_app": flask_app,
                    "account_id": account.id,
                    "app_id": app.id,
                    "app_config": app_config,
                    "conversation_id": conversation.id,
                    "message_id": message.id,
                    "agent_thoughts": list(agent_thoughts.values()),
                },
            ).start()

        def consume(agent_thought):
            merge_agent_thought(agent_thoughts, agent_thought)
            return {
                **stream_payload(agent_thought, agent_thoughts),
                "id": str(agent_thought.id),
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "task_id": str(agent_thought.task_id),
            }

        completed = False
        try:
            for agent_thought in agent_stream:
                data = consume(agent_thought)
                yield f"event: {agent_thought.event.value}\ndata: {json.dumps(data)}\n\n"
            completed = True
        finally:
            if completed:
                save_agent_thoughts()
            else:
                # GeneratorExit（客户端断连）时继续消费 Agent 的进程内队列，
                # 等正常/错误/停止终止事件出现后再持久化完整或部分结果。
                def drain_stream() -> None:
                    try:
                        for agent_thought in agent_stream:
                            consume(agent_thought)
                    finally:
                        save_agent_thoughts()

                Thread(target=drain_stream, kwargs={}).start()

    def stop_debug_chat(self, token: str, task_id: str, account: Account):
        """WEBAPP 关闭指定任务会话"""
        self.get_web_app(token)
        AgentQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, account.id)

    def get_conversations(self, token: str, is_pinned: bool, account: Account):
        """获取  WEBAPP 下的所有会话列表"""
        app = self.get_web_app(token)

        conversations = (
            self.db.session.query(Conversation)
            .filte(
                Conversation.app_id == app.id,
                Conversation.created_by == account.id,
                Conversation.invoke_from == InvokeFrom.WEB_APP,
                Conversation.is_pinned == is_pinned,
                ~Conversation.is_deleted,
            )
            .order_by(desc("created_at"))
            .all()
        )

        return conversations
