from dataclasses import dataclass

from flask import current_app
from injector import inject

from internal.core.language_model.language_model_manager import LanguageModelManager
from internal.core.memory.token_buffer_memory import TokenBufferMemory
from internal.entity.conversation_entity import InvokeFrom, MessageStatus
from internal.model.account import Account
from internal.model.conversation import Message
from internal.service.base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class AssistantAgentService(BaseService):
    """辅助AGENT服务"""

    db: SQLAlchemy
    language_model_manager: LanguageModelManager

    def chat(self, query, account: Account):
        """辅助智能体对话"""
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
        llm = self.language_model_manager.create_system_chat_model(temperature=0.8)

        # 提取记忆
        token_buffer_memory = TokenBufferMemory(
            db=self.db,
            conversation=conversation,
            model_instance=llm,
        )
        history = token_buffer_memory.get_history_prompt_messages(message_limit=3)
