#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   provider_entity
@Time   :   2026/5/14 14:56
@Author :   s.qiu@foxmail.com
"""

from typing import Type, Union

from pydantic import BaseModel, Field

from .model_entity import ModelEntity, ModelType, BaseLanguageModel


class ProviderEntity(BaseModel):
    """模型提供商实体"""

    name: str = ""  # 提供商的名字
    label: str = ""  # 提供商的标签
    description: str = ""  # 提供商的描述信息
    icon: str = ""  # 提供商的图标
    background: str = ""  # 提供商的图标背景
    supported_model_types: list[ModelType] = Field(
        default_factory=list
    )  # 支持的模型类型


class Provider(BaseModel):
    """大语言模型服务提供商 该类下可以获取该服务商的所有大语言模型、描述、图标、标签等信息"""

    name: str  # 提供商名称
    position: int  # 提供商位置信息
    provider_entity: ProviderEntity  # 模型提供商实体
    model_entity_map: dict[str, ModelEntity] = Field(
        default_factory=dict 
    )  # 模型实体映射
    model_calss_map: dict[str, Union[None, Type[BaseLanguageModel]]] = Field(
        default_factory=dict
    )  # 模型类映射
