#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File : language_model_manager.py
@Time : 2026/07/29
@Author : Youyou
"""

from typing import Any
import os
from pydantic import BaseModel, Field, model_validator
from .entities.provider_entity import Provider, ProviderEntity


class LanguageModelManager(BaseModel):
    """语言模型管理器"""

    provider_map: dict[str, Provider] = Field(default_factory=dict)

    @model_validator(pre=False)
    def validate_language_model_manager(clas, values: dict[str, Any]) -> dict[str, Any]:
        """预设规则校验 对管理器进行初始化"""
        current_path = os.path.abspath(__file__)
        providers_path = os.path.join(os.path.dirname(current_path), "providers")
        providers_yaml_path = os.path.join(providers_path, "providers.yaml")

        return values
