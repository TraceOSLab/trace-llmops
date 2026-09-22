#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   github_oauth
@Time   :   2026/1/27 21:11
@Author :   s.qiu@foxmail.com
"""
import urllib.parse

import requests

from .oauth import OAuth, OAuthUserInfo


class GithubOAuth(OAuth):
    """Github 授权认证"""
    _AUTHORIZE_URL = "https://github.com/login/oauth/authorize"  # 跳转授权接口 ? 拼接参数
    _ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"  # 获取授权令牌接口
    _USER_INFO_URL = "https://api.github.com/user"  # 获取用户信息接口
    _EMAIL_INFO_URL = "https://api.github.com/user/emails"  # 获取用户邮箱接口

    def get_provider(self) -> str:
        return "github"

    def get_authorization_url(self) -> str:
        """获取跳转授权认证的URL地址"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user:email",  # 只请求用户的基本信息
        }
        return f"{self._AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, code: str) -> str:
        """根据传入的code获取授权令牌"""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        headers = {"Accept": "application/json"}

        # 获取数据 提取 access_token
        resp = requests.post(self._ACCESS_TOKEN_URL, data=data, headers=headers)
        resp.raise_for_status()
        resp_json = resp.json()

        access_token = resp_json.get("access_token")
        if not access_token:
            raise ValueError(f"Github OAUTH授权失败{resp_json}")
        return access_token

    def get_raw_user_info(self, token: str) -> dict:
        """根据传入的token获取OAuth原始信息"""
        headers = {"Authorization": f"token {token}"}

        # 获取数据
        resp = requests.get(self._USER_INFO_URL, headers=headers)
        resp.raise_for_status()
        raw_info = resp.json()

        # 获取用户的邮箱信息
        email_resp = requests.get(self._EMAIL_INFO_URL, headers=headers)
        email_resp.raise_for_status()
        email_info = email_resp.json()

        primary_email = next((email for email in email_info
                              if email.get("primary") is True
                              and email.get("verified") is True
                              and email.get("email")), None)
        if primary_email is None:
            raise ValueError("Github OAuth 需要已验证的主邮箱")
        return {**raw_info, "email": primary_email["email"]}

    def transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """将OAuth原始信息转换成OAuthUserInfo"""

        # 邮箱参与本地账号关联，不为缺失身份生成伪造邮箱。
        email = raw_info.get("email")
        if not raw_info.get("id") or not email:
            raise ValueError("Github OAuth 身份信息不完整")

        return OAuthUserInfo(
            id=str(raw_info.get("id")),
            name=str(raw_info.get("name") or raw_info.get("login") or raw_info["id"]),
            email=str(email),
        )
