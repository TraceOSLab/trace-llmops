#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   app_config_service
@Time   :   2026/2/26 14:35
@Author :   s.qiu@foxmail.com
"""

from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Union
from uuid import UUID

from flask import request
from injector import inject
from langchain_core.tools import BaseTool
from internal.exception import FailException, NotFoundException

from internal.core.language_model.entities.model_entity import ModelParameterType
from internal.core.language_model.language_model_manager import LanguageModelManager
from internal.core.tools.api_tools.providers import ApiProviderManager
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager
from internal.core.workflow.entities.workflow_entity import WorkflowConfig
from internal.core.tools.api_tools.entities import ToolEntity
from internal.entity.app_entity import DEFAULT_APP_CONFIG
from internal.entity.workflow_entity import WorkflowStatus
from internal.lib.helper import datetime_to_timestamp, get_value_type
from internal.core.workflow import Workflow as WorkflowTool
from internal.model import (
    App,
    ApiTool,
    Dataset,
    AppConfig,
    AppConfigVersion,
    AppDatasetJoin,
)
from internal.model.workflow import Workflow
from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService


@inject
@dataclass
class AppConfigService(BaseService):
    """应用配置 服务"""

    db: SQLAlchemy
    api_provider_manager: ApiProviderManager
    builtin_provider_manager: BuiltinProviderManager
    language_model_manager: LanguageModelManager

    def get_app_config(self, app: App) -> dict[str, Any]:
        """读取运行配置；过滤失效引用，不在读取时改写已发布快照。"""
        config = app.app_config
        if config is None:
            raise FailException("应用运行配置不存在")
        dataset_ids = [str(join.dataset_id) for join in config.app_dataset_joins]
        return self._resolve_app_config(app, config, dataset_ids)

    def get_draft_app_config(self, app: App) -> dict[str, Any]:
        config = app.draft_app_config
        return self._resolve_app_config(app, config, config.datasets)

    def _resolve_app_config(self, app: App, config, dataset_ids) -> dict[str, Any]:
        model = self._process_and_validate_model_config(config.model_config)
        tools, _ = self._process_and_validate_tools(config.tools, app.account_id)
        datasets, _ = self._process_and_validate_datasets(dataset_ids, app.account_id)
        workflows, _ = self._process_and_validate_workflows(config.workflows, app.account_id)
        return deepcopy(self._process_and_transformer_app_config(
            model, tools, workflows, datasets, config,
        ))

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

    def get_langchain_tools_by_workflow_ids(
        self, workflow_ids: list[UUID]
    ) -> list[BaseTool]:
        """根据传递的工作流配置列表获取langchain工具列表"""
        # 根据传递的工作流id查询工作流记录信息
        workflow_records = (
            self.db.session.query(Workflow)
            .filter(
                Workflow.id.in_(workflow_ids),
                Workflow.status == WorkflowStatus.PUBLISHED,
            )
            .all()
        )

        # 2.循环遍历所有工作流记录列表
        workflows = []
        for workflow_record in workflow_records:
            try:
                # 3.创建工作流工具
                workflow_tool = WorkflowTool(
                    workflow_config=WorkflowConfig(
                        account_id=workflow_record.account_id,
                        name=f"wf_{workflow_record.tool_call_name}",
                        description=workflow_record.description,
                        nodes=workflow_record.graph.get("nodes", []),
                        edges=workflow_record.graph.get("edges", []),
                    )
                )
                workflows.append(workflow_tool)
            except Exception:
                continue

        return workflows

    @classmethod
    def _process_and_transformer_app_config(
        cls,
        model_config: dict[str, Any],
        tools: list[dict],
        workflows: list[dict],
        datasets: list[dict],
        app_config: Union[AppConfig, AppConfigVersion],
    ) -> dict[str, Any]:
        """根据传递的插件列表、工作流列表、知识库列表以及应用配置创建字典信息"""
        return {
            "id": str(app_config.id),
            "model_config": model_config,
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
        self, origin_datasets: list[dict], account_id: UUID
    ) -> tuple[list[dict], list[dict]]:
        """对知识库进行校验和处理"""
        datasets = []
        dataset_records = (
            self.db.session.query(Dataset).filter(
                Dataset.id.in_(origin_datasets), Dataset.account_id == account_id,
            ).all()
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
        self, origin_tools: list[dict], account_id: UUID
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
                        ApiTool.account_id == account_id,
                    )
                    .one_or_none()
                )
                if not tool_record:
                    continue

                # 校验通过 添加数据
                validate_tools.append(tool)
                provider = tool_record.provider
                if provider is None or provider.account_id != account_id:
                    validate_tools.pop()
                    continue
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
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])

        model_config = {
            "parameters": origin_model_config.get("parameters", {}),
            "provider": origin_model_config.get("provider", ""),
            "model": origin_model_config.get("model", ""),
        }

        # provider 是否合规，否则返回默认值
        if not model_config["provider"] or not isinstance(
            model_config["provider"], str
        ):
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])
        try:
            provider = self.language_model_manager.get_provider(model_config["provider"])
        except NotFoundException:
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])
        if not provider:
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])

        # model 是否合规，否则返回默认值
        if not model_config["model"] or not isinstance(model_config["model"], str):
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])
        try:
            model_entity = provider.get_model_entity(model_config["model"])
        except NotFoundException:
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])
        if not model_entity:
            return deepcopy(DEFAULT_APP_CONFIG["model_config"])

        if not isinstance(model_config["parameters"], dict):
            model_config["parameters"] = {}

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

    def _process_and_validate_workflows(
        self, origin_workflows: list[UUID], account_id: UUID
    ) -> tuple[list[dict], list[UUID]]:
        """工作流配置 提取数据 获取工作流信息"""
        workflows = []
        workflow_records = (
            self.db.session.query(Workflow)
            .filter(
                Workflow.id.in_(origin_workflows),
                Workflow.account_id == account_id,
                Workflow.status == WorkflowStatus.PUBLISHED,
            )
            .all()
        )
        workflow_dict = {
            str(workflow_record.id): workflow_record
            for workflow_record in workflow_records
        }
        workflow_sets = set(workflow_dict.keys())

        # 计算存在的工作流id列表，为了保留原始顺序，使用列表循环的方式来判断
        validate_workflows = [
            workflow_id
            for workflow_id in origin_workflows
            if workflow_id in workflow_sets
        ]

        # 循环获取工作流数据
        for workflow_id in validate_workflows:
            workflow = workflow_dict.get(str(workflow_id))
            workflows.append(
                {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "icon": workflow.icon,
                    "description": workflow.description,
                }
            )

        return workflows, validate_workflows
