#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   app_config_service
@Time   :   2026/2/26 14:35
@Author :   s.qiu@foxmail.com
"""

from dataclasses import dataclass
from typing import Any, Union

from flask import request
from injector import inject
from langchain_core.tools import BaseTool
from requests.utils import DEFAULT_ACCEPT_ENCODING

from internal.core.language_model.entities.model_entity import ModelParameterType
from internal.core.language_model.language_model_manager import LanguageModelManager
from internal.core.tools.api_tools.providers import ApiProviderManager
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.entity.app_entity import DEFAULT_APP_CONFIG
from internal.lib.helper import datetime_to_timestamp, get_value_type
from internal.model import (
    App,
    ApiTool,
    Dataset,
    AppConfig,
    AppConfigVersion,
    AppDatasetJoin,
)
from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService
from ..core.tools.api_tools.entities import ToolEntity


@inject
@dataclass
class AppConfigService(BaseService):
    """应用配置 服务"""

    db: SQLAlchemy
    api_provider_manager: ApiProviderManager
    builtin_provider_manager: BuiltinProviderManager
    language_model_manager: LanguageModelManager

    def get_app_config(self, app: App) -> dict[str, Any]:
        """获取该应用的运行配置"""
        app_config = app.app_config

        # 校验工具列表 是否需要更新草稿配置中的工具配置
        tools, validate_tools = self._process_and_validate_tools(app_config.tools)
        if app_config.tools != validate_tools:
            self.update(app_config, tools=validate_tools)

        # 校验知识库列表 是否需要更新草稿配置中的知识库配置
        app_dataset_joins = app_config.app_dataset_joins
        origin_datasets = [
            str(app_dataset_join.dataset_id) for app_dataset_join in app_dataset_joins
        ]
        datasets, validate_datasets = self._process_and_validate_datasets(
            origin_datasets
        )

        # 6.判断是否存在已删除的知识库，如果存在则更新
        for dataset_id in set(origin_datasets) - set(validate_datasets):
            with self.db.auto_commit():
                self.db.session.query(AppDatasetJoin).filter(
                    AppDatasetJoin.dataset_id == dataset_id
                ).delete()

        # todo:7 校验工作流列表
        workflows = []

        return self._process_and_transformer_app_config(
            tools, workflows, datasets, app_config
        )

    def get_draft_app_config(self, app: App) -> dict[str, Any]:
        """获取该应用的草稿配置"""

        draft_app_config = app.draft_app_config

        # 校验 model_config 配置, 如果使用不存在的模型，使用默认值填充
        validate_model_config = self._process_and_validate_model_config(draft_app_config.model_config)
        if draft_app_config.model_config != validate_model_config:
          self.update(draft_app_config, model_config=validate_model_config)

        # 校验工具列表 是否需要更新草稿配置中的工具配置
        tools, validate_tools = self._process_and_validate_tools(draft_app_config.tools)

        # 判断是否需要更新草稿配置中的工具列表信息
        if draft_app_config.tools != validate_tools:
            self.update(draft_app_config, tools=validate_tools)

        # 校验知识库列表 是否需要更新草稿配置中的知识库配置
        datasets, validate_datasets = self._process_and_validate_datasets(
            draft_app_config.datasets
        )
        if set(validate_datasets) != set(draft_app_config.datasets):
            self.update(draft_app_config, datasets=validate_datasets)

        # todo:7校验工作流列表
        workflows = []

        return self._process_and_transformer_app_config(
            tools, workflows, datasets, draft_app_config
        )

    def get_langchain_tools_by_tools_config(
        self, tools_config: list[dict]
    ) -> list[BaseTool]:
        # 工具配置转换为 LangChain 工具
        tools = []
        for tool in tools_config:
            if tool["type"] == "builtin_tool":
                builtin_tool = self.builtin_provider_manager.get_tool(
                    tool["provider"]["id"], tool["tool"]["name"]
                )
                if not builtin_tool:
                    continue
                tools.append(builtin_tool(**tool["tool"]["params"]))
            else:
                api_tool = self.get(ApiTool, tool["tool"]["id"])
                if not api_tool:
                    continue
                tools.append(
                    self.api_provider_manager.get_tool(
                        ToolEntity(
                            id=str(api_tool.id),
                            name=api_tool.name,
                            url=api_tool.url,
                            method=api_tool.method,
                            description=api_tool.description,
                            headers=api_tool.provider.headers,
                            parameters=api_tool.parameters,
                        )
                    )
                )
        return tools

    @classmethod
    def _process_and_transformer_app_config(
        cls,
        tools: list[dict],
        workflows: list[dict],
        datasets: list[dict],
        app_config: Union[AppConfig, AppConfigVersion],
    ) -> dict[str, Any]:
        """根据传递的插件列表、工作流列表、知识库列表以及应用配置创建字典信息"""
        return {
            "id": str(app_config.id),
            "model_config": app_config.model_config,
            "dialog_round": app_config.dialog_round,
            "preset_prompt": app_config.preset_prompt,
            "tools": tools,
            "workflows": workflows,
            "datasets": datasets,
            "retrieval_config": app_config.retrieval_config,
            "long_term_memory": app_config.long_term_memory,
            "opening_statement": app_config.opening_statement,
            "opening_questions": app_config.opening_questions,
            "speech_to_text": app_config.speech_to_text,
            "text_to_speech": app_config.text_to_speech,
            "suggested_after_answer": app_config.suggested_after_answer,
            "review_config": app_config.review_config,
            "updated_at": datetime_to_timestamp(app_config.updated_at),
            "created_at": datetime_to_timestamp(app_config.created_at),
        }

    def _process_and_validate_datasets(
        self, origin_datasets: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """对知识库进行校验和处理"""
        datasets = []
        dataset_records = (
            self.db.session.query(Dataset).filter(Dataset.id.in_(origin_datasets)).all()
        )
        dataset_dict = {
            str(dataset_record.id): dataset_record for dataset_record in dataset_records
        }
        dataset_sets = set(dataset_dict.keys())

        # 计算存在的知识库 保留原始顺序
        validate_datasets = [
            dataset_id for dataset_id in origin_datasets if dataset_id in dataset_sets
        ]

        # 获取组装知识库数据
        for dataset_id in validate_datasets:
            dataset = dataset_dict.get(dataset_id)
            datasets.append(
                {
                    "id": str(dataset.id),
                    "name": dataset.name,
                    "icon": dataset.icon,
                    "description": dataset.description,
                }
            )
        return datasets, validate_datasets

    def _process_and_validate_tools(
        self, origin_tools: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """对工具信息进行校验和处理"""

        tools = []
        validate_tools = []

        # 遍历工具 校验工具是否使用不存在的工具 需要剔除数据并更新
        for tool in origin_tools:
            if tool["type"] == "builtin_tool":
                # 查询内置工具提供者 检测是否存在
                provider = self.builtin_provider_manager.get_provider(
                    tool["provider_id"]
                )
                if not provider:
                    continue

                # 获取工具提供者下的工具实体 检测是否存在
                tool_entity = provider.get_tool_entity(tool["tool_id"])
                if not tool_entity:
                    continue

                # 校验通过 检测工具的params与草稿中的params是否一致 不一致需全部重置
                params = tool["params"]
                param_keys = set([param.name for param in tool_entity.params])
                if set(tool["params"].keys()) - param_keys:
                    # 构建新的params
                    params = {
                        param.name: param.default
                        for param in tool_entity.params
                        if param.default is not None
                    }

                # 校验通过
                validate_tools.append({**tool, "params": params})

                # 组装内置工具信息
                provider_entity = provider.provider_entity
                tools.append(
                    {
                        "type": "builtin_tool",
                        "provider": {
                            "id": provider_entity.name,
                            "name": provider_entity.name,
                            "label": provider_entity.label,
                            "icon": f"{request.scheme}://{request.host}/builtin-tools/{provider_entity.name}/icon",
                            "description": provider_entity.description,
                        },
                        "tool": {
                            "id": tool_entity.name,
                            "name": tool_entity.name,
                            "label": tool_entity.label,
                            "description": tool_entity.description,
                            "params": tool["params"],
                        },
                    }
                )

            elif tool["type"] == "api_tool":
                # 查询数据库获取对应工具 检测是否存在
                tool_record = (
                    self.db.session.query(ApiTool)
                    .filter(
                        ApiTool.provider_id == tool["provider_id"],
                        ApiTool.name == tool["tool_id"],
                    )
                    .one_or_none()
                )
                if not tool_record:
                    continue

                # 校验通过 添加数据
                validate_tools.append(tool)
                provider = tool_record.provider
                tools.append(
                    {
                        "type": "api_tool",
                        "provider": {
                            "id": str(provider.id),
                            "name": provider.name,
                            "label": provider.name,
                            "icon": provider.icon,
                        },
                        "tool": {
                            "id": str(tool_record.id),
                            "name": tool_record.name,
                            "label": tool_record.name,
                            "description": tool_record.description,
                            "params": {},
                        },
                    }
                )

        return tools, validate_tools

    def _process_and_validate_model_config(
        self, origin_model_config: dict[str, Any]
    ) -> dict[str, Any]:
        """根据传递的模型配置处理并校验，随后返回校验后的信息"""
        if not isinstance(origin_model_config, dict):
            return DEFAULT_APP_CONFIG["model_config"]

        model_config = {
            "parameters": origin_model_config.get("parameters", {}),
            "provider": origin_model_config.get("provider", ""),
            "model": origin_model_config.get("model", ""),
        }

        # provider 是否合规，否则返回默认值
        if not model_config["provider"] or not isinstance(
            model_config["provider"], str
        ):
            return DEFAULT_APP_CONFIG["model_config"]
        provider = self.language_model_manager.get_provider(model_config["provider"])
        if not provider:
            return DEFAULT_APP_CONFIG["model_config"]

        # model 是否合规，否则返回默认值
        if not model_config["model"] or not isinstance(model_config["model"], str):
            return DEFAULT_APP_CONFIG["model_config"]
        model_entity = provider.get_model_entity(model_config["model"])
        if not model_entity:
            return DEFAULT_ACCEPT_ENCODING["model_config"]

        # parameters 是否合规，否则返回默认值
        parameters = {}
        for parameter in model_entity.parameters:
            # 从model_config中获取参数值，如果不存在则设置为默认值
            parameter_value = model_config["parameters"].get(
                parameter.name, parameter.default
            )

            # 判断参数是否必填
            if parameter.required:
                # 参数必填，则值不允许为None，如果为None则设置默认值
                if parameter_value is None:
                    parameter_value = parameter.default
                else:
                    # 值非空则校验数据类型是否正确，不正确则设置默认值
                    if get_value_type(parameter_value) != parameter.type.value:
                        parameter_value = parameter.default
            else:
                # 参数非必填，数据非空的情况下需要校验
                if parameter_value is not None:
                    if get_value_type(parameter_value) != parameter.type.value:
                        parameter_value = parameter.default

            # 判断参数是否存在options，如果存在则数值必须在options中选择
            if parameter.options and parameter_value not in parameter.options:
                parameter_value = parameter.default

            # 参数类型为int/float，如果存在min/max时候需要校验
            if (
                parameter.type in [ModelParameterType.INT, ModelParameterType.FLOAT]
                and parameter_value is not None
            ):
                # 校验数值的min/max
                if (parameter.min and parameter_value < parameter.min) or (
                    parameter.max and parameter_value > parameter.max
                ):
                    parameter_value = parameter.default

            parameters[parameter.name] = parameter_value

        # 完成数据校验，赋值parameters参数
        model_config["parameters"] = parameters

        return model_config
