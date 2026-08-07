#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   provider_entity
@Time   :   2026/5/14 14:56
@Author :   s.qiu@foxmail.com
"""

from typing import Any, Type, Union

from internal.lib.helper import dynamic_import
from pydantic import BaseModel, Field, model_validator

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
    model_class_map: dict[str, Union[None, Type[BaseLanguageModel]]] = Field(
        default_factory=dict
    )  # 模型类映射

    @model_validator(pre=False)
    def validate_provider(cls, provider: dict[str, Any]) -> dict[str, Any]:
        """校验器 完成服务提供者的实体与类实例化"""

        # 服务提供商实体
        provider_entity: ProviderEntity = provider["provider_entity"]

        # 动态导入服务 提供商的模型类
        for model_type in provider_entity["supported_model_types"]:
            symbol_name = model_type[0].upper() + model_type[1:]
            provider["model_class_map"][model_type] = dynamic_import(
                f"internal.core.language_model.providers.{provider_entity.name}.{model_type}",
                symbol_name,
            )

        # 读取位置信息文件 获取模型名字

        # 根据位置信息名称 组装对应模型详细信息

        return provider
