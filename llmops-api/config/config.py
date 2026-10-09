#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   config.py
@Time   :   2025/9/9 15:48
@Author :   s.qiu@foxmail.com
"""

import os
from typing import Any
from urllib.parse import quote

from .default_config import DEFAULT_CONFIG


def _get_env(key: str) -> Any:
    """从环境变量中获取配置项 如果没有返回默认配置"""
    return os.environ.get(key, DEFAULT_CONFIG.get(key))


def _get_bool_env(key: str) -> bool:
    """从环境变量中获取布尔配置项 找不到返回 False"""
    value: str = _get_env(key)
    return value.lower() == "true" if value is not None else False


class Config:
    """初始化配置"""

    def __init__(self):
        self.WTF_CSRF_ENABLED = _get_bool_env("WTF_CSRF_ENABLED")
        self.SQLALCHEMY_DATABASE_URI = _get_env("SQLALCHEMY_DATABASE_URI")
        self.SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": int(_get_env("SQLALCHEMY_POOL_SIZE")),
            "pool_recycle": int(_get_env("SQLALCHEMY_POOL_RECYCLE")),
        }
        self.SQLALCHEMY_ECHO = _get_bool_env("SQLALCHEMY_ECHO")

        # Weaviate 向量数据库配置
        self.WEAVIATE_HTTP_HOST = _get_env("WEAVIATE_HTTP_HOST")
        self.WEAVIATE_HTTP_PORT = int(_get_env("WEAVIATE_HTTP_PORT"))
        self.WEAVIATE_GRPC_HOST = _get_env("WEAVIATE_GRPC_HOST")
        self.WEAVIATE_GRPC_PORT = int(_get_env("WEAVIATE_GRPC_PORT"))
        self.WEAVIATE_API_KEY = (_get_env("WEAVIATE_API_KEY") or "").strip() or None

        # Redis配置
        self.REDIS_HOST = _get_env("REDIS_HOST")
        self.REDIS_PORT = _get_env("REDIS_PORT")
        self.REDIS_USERNAME = _get_env("REDIS_USERNAME")
        self.REDIS_PASSWORD = _get_env("REDIS_PASSWORD")
        self.REDIS_DB = _get_env("REDIS_DB")
        self.REDIS_USE_SSL = _get_bool_env("REDIS_USE_SSL")

        # Celery配置
        redis_auth = ""
        if self.REDIS_USERNAME or self.REDIS_PASSWORD:
            username = quote(self.REDIS_USERNAME or "", safe="")
            password = quote(self.REDIS_PASSWORD or "", safe="")
            redis_auth = f"{username}:{password}@"
        redis_url = f"redis://{redis_auth}{self.REDIS_HOST}:{self.REDIS_PORT}"
        self.CELERY = {
            "broker_url": f"{redis_url}/{int(_get_env('CELERY_BROKER_DB'))}",
            "result_backend": f"{redis_url}/{int(_get_env('CELERY_RESULT_BACKEND_DB'))}",
            "task_ignore_result": _get_bool_env("CELERY_TASK_IGNORE_RESULT"),
            "result_expires": int(_get_env("CELERY_RESULT_EXPIRES")),
            "broker_connection_retry_on_startup": _get_bool_env(
                "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP"
            ),
        }

        # 辅助Agent应用id标识
        self.ASSISTANT_AGENT_ID = _get_env("ASSISTANT_AGENT_ID")
