#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   account
@Time   :   2026/1/26 21:27
@Author :   s.qiu@foxmail.com
"""

from flask import current_app
from flask_login import UserMixin
from sqlalchemy import (
    Column,
    UUID,
    String,
    DateTime,
    text,
    PrimaryKeyConstraint,
)

from internal.entity.conversation_entity import InvokeFrom
from internal.extension.database_extension import db
from internal.model.conversation import Conversation


class Account(UserMixin, db.Model):
    """账号模型"""

    __tablename__ = "account"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_account_id"),)

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    name = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    email = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    avatar = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    password = Column(
        String(255), nullable=True, server_default=text("''::character varying")
    )
    password_salt = Column(
        String(255), nullable=True, server_default=text("''::character varying")
    )
    last_login_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )
    last_login_ip = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        server_onupdate=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )
    assistant_agent_conversation_id = Column(UUID, nullable=True)  # 辅助智能体会话id

    @property
    def is_password_set(self) -> bool:
        """只读属性，获取当前账号的密码是否设置"""
        return self.password is not None and self.password != ""

    @property
    def assistant_agent_conversation(self) -> Conversation:
        """只读属性 返回当前账号辅助AGENT的会话信息"""
        assistant_agent_id = current_app.config.get("ASSISTANT_AGENT_ID")

        assistant_conversation = (
            db.session.query(Conversation).get(self.assistant_agent_conversation_id)
            if assistant_agent_id
            else None
        )

        if not self.assistant_agent_conversation_id or not assistant_conversation:
            with db.auto_commit:
                assistant_conversation = Conversation(
                    app_id=assistant_agent_id,
                    name="New Conversation",
                    invoke_from=InvokeFrom.ASSISTANT_AGENT,
                    created_by=self.id,
                )
                db.session.add(assistant_conversation)
                db.session.flush()
                # 更新最新的 id
                self.assistant_agent_conversation_id = assistant_conversation.id

        return assistant_conversation


class AccountOAuth(db.Model):
    """账号与第三方授权认证记录表"""

    __tablename__ = "account_oauth"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_account_oauth_id"),)

    id = Column(UUID, nullable=False, server_default=text("uuid_generate_v4()"))
    account_id = Column(UUID, nullable=False)
    provider = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    openid = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    encrypted_token = Column(
        String(255), nullable=False, server_default=text("''::character varying")
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        server_onupdate=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )
