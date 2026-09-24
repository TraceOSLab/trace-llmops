from dataclasses import dataclass
from uuid import UUID

from flask import request
from flask_login import current_user, login_required
from injector import inject

from internal.service import ConversationService
from internal.schema.conversation_schema import (
    GetConversationMessagesWithPageReq,
    GetConversationMessagesWithPageResp,
    UpdateConversationNameReq,
    UpdateConversationIsPinnedReq,
)
from pkg.paginator.paginator import PageModel
from pkg.response.response import success_json, success_message, validate_error_json


@inject
@dataclass
class ConversationHandler:
    """会话处理器"""

    conversation_service: ConversationService

    @login_required
    def get_conversation_messages_with_page(self, conversation_id: UUID):
        """获取当前账号下该会话的消息分页列表"""
        req = GetConversationMessagesWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        messages, paginator = (
            self.conversation_service.get_conversation_messages_with_page(
                conversation_id, req, current_user
            )
        )

        resp = GetConversationMessagesWithPageResp(many=True)

        return success_json(PageModel(list=resp.dump(messages), paginator=paginator))

    @login_required
    def delete_conversation(self, conversation_id: UUID):
        """删除指定的会话记录"""
        self.conversation_service.delete_conversation(conversation_id, current_user)
        return success_message("删除会话成功")

    @login_required
    def delete_message(self, conversation_id: UUID, message_id: UUID):
        """删除指定的消息记录"""
        self.conversation_service.delete_message(
            conversation_id, message_id, current_user
        )

        return success_message("删除会话消息成功")

    @login_required
    def get_conversation_name(self, conversation_id: UUID):
        """获取指定会话的名称"""
        conversation = self.conversation_service.get_conversation(
            conversation_id, current_user
        )
        return success_json({"name": conversation.name})

    @login_required
    def update_conversation_name(self, conversation_id: UUID):
        """更改指定会话的名称"""
        req = UpdateConversationNameReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.conversation_service.update_conversation(
            conversation_id, current_user, name=req.name.data
        )

        return success_message("修改会话名称成功")

    @login_required
    def update_conversation_is_pinned(self, conversation_id: UUID):
        """更新指定会话的置顶状态"""
        req = UpdateConversationIsPinnedReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.conversation_service.update_conversation(
            conversation_id, current_user, is_pinned=req.is_pinned.data
        )

        return success_message("修改会话置顶状态成功")
