#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File : chat.py
@Time : 2026/07/29
@Author : Youyou
"""

from langchain_openai import ChatOpenAI

from internal.core.language_model.entities.model_entity import BaseLanguageModel


class Chat(ChatOpenAI, BaseLanguageModel):
    """OpenAI聊天模型基类"""

    pass
