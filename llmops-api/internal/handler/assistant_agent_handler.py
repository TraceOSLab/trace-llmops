from dataclasses import dataclass

from flask_login import current_user
from injector import inject
from uuid import UUID
from internal.schema.assistant_agent_schema import AssistantAgentChat
from pkg.response.response import (
    compact_generate_response,
    success_message,
    validate_error_json,
)
from internal.service import AssistantAgentService


@inject
@dataclass
class AssistantAgentHandler:
    """辅助AGNENT模块处理器"""

    assistant_agent_service: AssistantAgentService

    def assistant_agent_chat(self):
        """辅助智能体对话"""
        req = AssistantAgentChat()
        if not req.validate():
            return validate_error_json(req.errors)

        # 2.调用服务创建会话响应
        response = self.assistant_agent_service.chat(req.query.data, current_user)

        return compact_generate_response(response)

    def stop_assistant_agent_chat(self, task_id: UUID):
        """辅助智能体停止会话"""
        self.assistant_agent_service.stop_assistant_agent_chat(task_id, current_user)
        return success_message("停止会话成功")
