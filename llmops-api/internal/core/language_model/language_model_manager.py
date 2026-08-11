#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File : language_model_manager.py
@Time : 2026/07/29
@Author : Youyou
"""

from typing import Any, Optional, Type
import os
from injector import inject, singleton
from pydantic import BaseModel, Field, model_validator
import yaml

from internal.exception.exception import NotFoundException
from .entities.provider_entity import Provider, ProviderEntity
from .entities.model_entity import ModelType, BaseLanguageModel


@inject
@singleton
class LanguageModelManager(BaseModel):
    """语言模型管理器"""

    provider_map: dict[str, Provider] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_language_model_manager(self) -> dict[str, Any]:
        """预设规则校验 对管理器进行初始化"""
        current_path = os.path.abspath(__file__)
        providers_path = os.path.join(os.path.dirname(current_path), "providers")
        providers_yaml_path = os.path.join(providers_path, "providers.yaml")

        # 读取 providers.yaml 获取提供商列表
        with open(providers_yaml_path, encoding="utf-8") as f:
            providers_yaml_data = yaml.safe_load(f)

        self.provider_map = {}
        for index, provider_yaml_data in enumerate(providers_yaml_data):
            # 构建提供商实体
            provider_entity = ProviderEntity(**provider_yaml_data)
            self.provider_map[provider_entity.name] = Provider(
                name=provider_entity.name,
                position=index + 1,
                provider_entity=provider_entity,
            )

        return self

    def get_providers(self) -> list[Provider]:
        """获取所有提供者列表信息"""
        return list(self.provider_map.values())

    def get_provider(self, provider_name: str) -> Optional[Provider]:
        """根据提供商名称获取提供商"""
        provider = self.provider_map.get(provider_name, None)
        if provider is None:
            raise NotFoundException("该提供商不存在!")
        return provider

    def get_model_class_by_provider_and_type(
        self,
        provider_name: str,
        model_type: ModelType,
    ) -> Optional[Type[BaseLanguageModel]]:
        """根据提供商名称+模型类型，获取模型类"""
        provider = self.get_provider(provider_name)

        return provider.get_model_class(model_type)

    def get_model_class_by_provider_and_model(
        self,
        provider_name: str,
        model_name: str,
    ) -> Optional[Type[BaseLanguageModel]]:
        """根据传递的提供者名字+模型名字获取模型类"""
        # 1.根据名字获取提供者信息
        provider = self.get_provider(provider_name)

        # 2.在提供者下获取该模型实体
        model_entity = provider.get_model_entity(model_name)

        return provider.get_model_class(model_entity.model_type)
