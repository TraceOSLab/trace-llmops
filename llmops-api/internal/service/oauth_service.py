#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   oauth_service
@Time   :   2026/1/27 21:02
@Author :   s.qiu@foxmail.com
"""
import os
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flask import request
from injector import inject
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from internal.exception import FailException, NotFoundException, UnauthorizedException
from pkg.oauth import OAuth, GithubOAuth
from pkg.sqlalchemy import SQLAlchemy
from . import AccountService
from .base_service import BaseService
from .jwt_service import JWTService
from ..model import Account, AccountOAuth


OAUTH_LOCK_TIMEOUT = "5s"


@inject
@dataclass
class OAuthService(BaseService):
    """第三方授权认证服务"""

    db: SQLAlchemy
    jwt_service: JWTService
    account_service: AccountService

    @classmethod
    def get_all_oauth(cls) -> dict[str, OAuth]:
        """获取项目支持的第三方授权认证方式"""
        # 1.实例化集成的第三方授权认证OAuth
        github = GithubOAuth(
            client_id=os.getenv("GITHUB_CLIENT_ID"),
            client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
            redirect_uri=os.getenv("GITHUB_REDIRECT_URI"),
        )

        return {"github": github}

    @classmethod
    def get_oauth_by_provider_name(cls, provider_name: str) -> OAuth:
        """根据传递的服务提供商名字获取授权服务"""
        all_oauth = cls.get_all_oauth()
        oauth = all_oauth.get(provider_name)

        if oauth is None:
            raise NotFoundException(f"该授权方式[{provider_name}]不存在")

        return oauth

    def oauth_login(self, provider_name: str, code: str) -> dict[str, Any]:
        """第三方授权登录 反回凭证信息"""
        oauth = self.get_oauth_by_provider_name(provider_name)
        oauth_access_token = oauth.get_access_token(code)
        oauth_user_info = oauth.get_user_info(oauth_access_token)  # id/name/email

        # 外部请求在事务前完成；账号、绑定、登录状态和凭证生成作为一次操作。
        with self.db.auto_commit():
            self._lock_login_identity(provider_name, oauth_user_info.id, oauth_user_info.email)
            account_oauth = self.account_service.get_account_oauth_by_provider_name_and_openid(
                provider_name, oauth_user_info.id,
            )
            if account_oauth is None:
                account = self.account_service.get_account_by_email(oauth_user_info.email)
                if account is None:
                    account = Account(name=oauth_user_info.name, email=oauth_user_info.email)
                    self.db.session.add(account)
                    self.db.session.flush()
                account_oauth = AccountOAuth(
                    account_id=account.id, provider=provider_name,
                    openid=oauth_user_info.id, encrypted_token=oauth_access_token,
                )
                self.db.session.add(account_oauth)
            else:
                account = self.account_service.get_account(account_oauth.account_id)
                if account is None:
                    raise UnauthorizedException("授权绑定的账号不存在")

            account.last_login_at = datetime.now()
            account.last_login_ip = request.remote_addr
            account_oauth.encrypted_token = oauth_access_token
            expire_at = int((datetime.now() + timedelta(days=5)).timestamp())
            payload = {"sub": str(account.id), "iss": "llmops", "exp": expire_at}
            access_token = self.jwt_service.generate_token(payload)
        return {"expire_at": expire_at, "access_token": access_token}

    def _lock_login_identity(self, provider: str, openid: str, email: str) -> None:
        """在查询前串行化同身份或同邮箱登录；事务结束时由 PostgreSQL 释放。"""
        identities = [("oauth-identity", provider, openid), ("oauth-email", email)]
        keys = sorted({
            int.from_bytes(hashlib.sha256(json.dumps(identity).encode()).digest()[:8],
                           byteorder="big", signed=True)
            for identity in identities
        })
        previous_timeout = self.db.session.scalar(text("SELECT current_setting('lock_timeout')"))
        self.db.session.execute(
            text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": OAUTH_LOCK_TIMEOUT},
        )
        try:
            # 固定顺序避免两个请求分别持有邮箱/身份锁后相互等待。
            for key in keys:
                self.db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        except DBAPIError as error:
            if getattr(error.orig, "pgcode", None) == "55P03":
                # 超时会使事务失效；外层 auto_commit 回滚并释放已持有的锁。
                raise FailException("登录请求繁忙，请稍后重试") from None
            raise
        # 不改变本事务后续操作的锁等待配置；出错时由 rollback 恢复。
        self.db.session.execute(
            text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": previous_timeout},
        )
