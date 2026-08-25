#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   provider_entity
@Time   :   2026/5/14 14:56
@Author :   s.qiu@foxmail.com
"""

import os
from typing import Any, Optional, Type, Union

import yaml

from internal.core.language_model.entities.default_model_parameter_template import (
    DEFAULT_MODEL_PARAMETER_TEMPLATE,
)
from internal.exception.exception import FailException, NotFoundException
from internal.lib.helper import dynamic_import
from pydantic import BaseModel, Field, model_validator

from .model_entity import (
    BaseLanguageModel,
    ModelEntity,
    ModelType,
    StructuredOutputStrategy,
)


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
    visible: bool = True  # 是否在模型列表接口中展示
    api_key_env: str = ""  # API Key 对应的环境变量名
    base_url: str = ""  # Provider 默认 API 地址
    base_url_env: str = ""  # 可覆盖默认地址的环境变量名
    structured_output_strategy: StructuredOutputStrategy = (
        StructuredOutputStrategy.FUNCTION_CALLING
    )
    structured_output_strict: bool = False


class Provider(BaseModel):
    """大语言模型服务提供商 该类下可以获取该服务商的所有大语言模型、描述、图标、标签等信息"""

    name: str  # 提供商名称
    position: int  # 提供商位置信息
    provider_entity: ProviderEntity  # 模型提供商实体
    model_entity_map: dict[str, ModelEntity] = Field(
        default_factory=dict
    )  # 模型实体映射
    model_class_map: dict[ModelType, Union[None, Type[BaseLanguageModel]]] = Field(
        default_factory=dict
    )  # 模型类映射

    @model_validator(mode="after")
    def validate_provider(self) -> dict[str, Any]:
        """校验器 完成服务提供者的实体与类实例化"""

        # 服务提供商实体
        provider_entity: ProviderEntity = self.provider_entity

        # 1. 构建模型类映射
        # 动态导入服务
        for model_type in provider_entity.supported_model_types:
            symbol_name = model_type.value.capitalize()

            self.model_class_map[model_type] = dynamic_import(
                f"internal.core.language_model.providers.{provider_entity.name}.{model_type.value}",
                symbol_name,
            )

        # 2. 构建模型实体映射
        # 读取位置信息文件 获取模型名字
        current_path = os.path.abspath(__file__)
        entities_path = os.path.dirname(current_path)
        provider_path = os.path.join(
            os.path.dirname(entities_path), "providers", provider_entity.name
        )

        # 根据位置信息名称 组装对应模型详细信息
        positions_yaml_path = os.path.join(provider_path, "positions.yaml")
        with open(positions_yaml_path, encoding="utf_8") as f:
            positions_yaml_data = yaml.safe_load(f) or []
        if not isinstance(positions_yaml_data, list):
            raise FailException("positions.yaml数据格式错误")

        # 根据位置信息 读取模型名称 组装parameters部分
        for model_name in positions_yaml_data:
            model_yaml_path = os.path.join(provider_path, f"{model_name}.yaml")
            with open(model_yaml_path, encoding="utf_8") as f:
                model_yaml_data = yaml.safe_load(f)

            # 处理模型的parameters部分 是否使用默认值填充
            model_parameters = model_yaml_data.get("parameters") or []
            parameters = []
            for parameter in model_parameters:
                parameter = parameter.copy()
                use_template = parameter.get("use_template")
                # 如果是用来默认值那就使用模板填充 否则直接填充
                if use_template:
                    default_parameter = DEFAULT_MODEL_PARAMETER_TEMPLATE.get(
                        use_template
                    )
                    if default_parameter is None:
                        raise FailException(
                            f"模型{model_name}引用了不存在的参数模板: {use_template}"
                        )
                    del parameter["use_template"]
                    parameters.append({**default_parameter, **parameter})
                else:
                    parameters.append(parameter)

            model_yaml_data["parameters"] = parameters
            self.model_entity_map[model_name] = ModelEntity(**model_yaml_data)

        return self

    def get_model_class(
        self, model_type: ModelType
    ) -> Optional[Type[BaseLanguageModel]]:
        """根据 模型类型获取该提供者的模型类"""
        model_class = self.model_class_map.get(model_type, None)
        if model_class is None:
            raise NotFoundException("该模型类不存在")
        return model_class

    def get_model_entity(self, model_name: str) -> Optional[ModelEntity]:
        """根据模型名称获取模型实体"""
        model_entity = self.model_entity_map.get(model_name, None)
        if model_entity is None:
            raise NotFoundException("该模型实体不存在")
        return model_entity

    def get_model_entities(self) -> list[ModelEntity]:
        """获取该提供商模型实体列表"""
        return list(self.model_entity_map.values())

    def get_visible_model_entities(self) -> list[ModelEntity]:
        """获取该提供商可展示的模型实体列表。"""
        return [model for model in self.model_entity_map.values() if model.visible]
