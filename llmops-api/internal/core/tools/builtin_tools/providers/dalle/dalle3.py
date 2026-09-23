#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   dalle3
@Time   :   2025/11/28 15:14
@Author :   s.qiu@foxmail.com
"""
from langchain.tools import BaseTool
from langchain_community.tools.openai_dalle_image_generation import OpenAIDALLEImageGenerationTool
from langchain_community.utilities.dalle_image_generator import DallEAPIWrapper
from pydantic import BaseModel, Field
from typing import Literal

from internal.lib.helper import add_attribute


class Dalle3ArgsSchema(BaseModel):
    query: str = Field(description="输入应该是生成图像的文本提示(prompt)")


class Dalle3APIWrapper(DallEAPIWrapper):
    """当前 SDK 包装器未转发 style，显式传递目录中已有的参数。"""
    style: Literal["vivid", "natural"] = "vivid"
    size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1024x1024"

    def run(self, query: str) -> str:
        response = self.client.generate(
            prompt=query, n=self.n, size=self.size, model=self.model_name,
            style=self.style, **({"quality": self.quality} if self.quality else {}),
        )
        urls = [item.url for item in response.data if isinstance(item.url, str) and item.url]
        return self.separator.join(urls) if urls else "No image was generated"


@add_attribute("args_schema", Dalle3ArgsSchema)
def dalle3(**kwargs) -> BaseTool:
    """返回DALLE3绘图工具"""
    return OpenAIDALLEImageGenerationTool(
        api_wrapper=Dalle3APIWrapper(**{**kwargs, "model": "dall-e-3", "timeout": 60, "max_retries": 0}),
    )
