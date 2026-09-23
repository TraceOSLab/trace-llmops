#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   google_serper
@Time   :   2025/11/24 16:19
@Author :   s.qiu@foxmail.com
"""

from langchain.tools import BaseTool
from langchain_community.tools import GoogleSerperRun
from langchain_community.utilities import GoogleSerperAPIWrapper
from pydantic import BaseModel, Field
from contextlib import closing
import aiohttp
import requests

from internal.lib.helper import add_attribute


class GoogleSerperArgsSchema(BaseModel):
    """谷歌SerperAPI搜索参数描述"""
    query: str = Field(description="需要检索查询的语句.")


class BoundedGoogleSerperAPIWrapper(GoogleSerperAPIWrapper):
    """只补 SDK 的传输边界，沿用其搜索结果解析。"""

    def _request_args(self, search_term, search_type, kwargs):
        return {
            "url": f"https://google.serper.dev/{search_type}",
            "headers": {"X-API-KEY": self.serper_api_key or "", "Content-Type": "application/json"},
            "params": {"q": search_term, **{key: value for key, value in kwargs.items() if value is not None}},
        }

    def _google_serper_api_results(self, search_term, search_type="search", **kwargs):
        with closing(requests.post(**self._request_args(search_term, search_type, kwargs), timeout=(5, 30))) as response:
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict):
            raise ValueError("搜索响应格式错误")
        return result

    async def _async_google_serper_search_results(self, search_term, search_type="search", **kwargs):
        async def fetch(session):
            async with session.post(
                **self._request_args(search_term, search_type, kwargs),
                timeout=aiohttp.ClientTimeout(total=35, connect=5, sock_read=30),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                if not isinstance(result, dict):
                    raise ValueError("搜索响应格式错误")
                return result
        if self.aiosession is not None:
            return await fetch(self.aiosession)
        async with aiohttp.ClientSession() as session:
            return await fetch(session)


@add_attribute("args_schema", GoogleSerperArgsSchema)
def google_serper(**kwargs) -> BaseTool:
    """谷歌Serper搜索"""
    return GoogleSerperRun(
        name="google_serper",
        description="这是一个低成本的谷歌搜索API。当你需要搜索时事的时候，可以使用该工具，该工具的输入是一个查询语句",
        api_wrapper=BoundedGoogleSerperAPIWrapper(),
    )
