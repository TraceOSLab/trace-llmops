#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File : completion.py
@Time : 2026/07/29
@Author : Youyou
"""

from langchain_core.language_models import BaseLanguageModel
from langchain_openai import ChatOpenAI


class Completion(ChatOpenAI, BaseLanguageModel):
    """OpenAI聊天模型基类"""

    pass
