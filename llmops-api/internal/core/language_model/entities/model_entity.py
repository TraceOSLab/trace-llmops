#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   model_entity
@Time   :   2026/5/12
@Author :   s.qiu@foxmail.com
"""
from abc import ABC
from enum import Enum
from typing import Any, Optional

from langchain_core.language_models import BaseLanguageModel as LCBaseLanguageModel
from pydantic import BaseModel, Field


class DefaultModelParameterName(str, Enum):
    """默认的参数名字，一般是所有LLM都有的一些参数"""
    TEMPERATURE = "temperature"  # 温度
    TOP_P = "top_p"  # 核采样率
    PRESENCE_PENALTY = "presence_penalty"  # 存在惩罚
    FREQUENCY_PENALTY = "frequency_penalty"  # 频率惩罚
    MAX_COMPLETION_TOKENS = "max_completion_tokens"  # 要生成的内容的最大tokens数


class ModelType(str, Enum):
    CHAT = "chat"  # 对话模型
    COMPLETION = "completion"  # 文本生成模型


class ModelParameterType(str, Enum):
    """模型参数类型"""
    FLOAT = "float"
    INT = "int"
    STRING = "string"
    BOOLEAN = "boolean"


class ModelParameterOption(BaseModel):
    """模型参数选项实体"""
    label: str = ""  # 选项标签
    value: Any = None  # 选项值


class ModelParameter(BaseModel):
    """模型参数实体"""
    name: str = ""  # 参数名
    label: str = ""  # 参数标签
    type: ModelParameterType = ModelParameterType.STRING  # 参数类型
    help: str = ""  # 提示信息
    required: bool = False  # 是否必填
    default: Optional[Any] = None  # 默认值
    min: Optional[float] = None  # 最小值
    max: Optional[float] = None  # 最大值
    precision: Optional[int] = None  # 精度
    options: list[ModelParameterOption] = Field(default_factory=list)  # 选项数据源


class ModelEntity(BaseModel):
    """语言模型实体 模型相关信息"""
    model_name: str = Field(default="", alias="model")
    label: str = Field(default="", alias="label")
    model_type: ModelType = ModelType.CHAT
    context_window: int = 0  # 上下文窗口长度
    max_output_tokens: int = 0  # 最大输出token数
    attributes: dict[str, Any] = Field(default_factory=dict)  # 模型属性
    parameters: dict[str, Any] = Field(default_factory=dict)  # 模型参数
    metadata: dict[str, Any] = Field(default_factory=dict)  # 模型元数据


class BaseLanguageModel(LCBaseLanguageModel, ABC):
    """基础语言模型"""
