#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   provider_entity
@Time   :   2026/5/14 14:56
@Author :   s.qiu@foxmail.com
"""
from pydantic import BaseModel, Field

from internal.core.language_model.entities.model_entity import ModelType


class ProviderEntity(BaseModel):
    """模型提供商实体"""
    name: str = ""  # 提供商的名字
    label: str = ""  # 提供商的标签
    description: str = ""  # 提供商的描述信息
    icon: str = ""  # 提供商的图标
    background: str = ""  # 提供商的图标背景
    supported_model_types: list[ModelType] = Field(default_factory=list)  # 支持的模型类型
