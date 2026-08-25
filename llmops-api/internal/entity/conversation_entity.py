#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   conversation_entity
@Time   :   2026/1/21 11:07
@Author :   s.qiu@foxmail.com
"""
from enum import Enum

from pydantic import BaseModel, Field

# 汇总摘要 提示词
SUMMARIZER_TEMPLATE = """
你是一个“对话增量总结助手”。

任务：
- 基于已有总结和新的会话内容生成新的总结。
- 保留已有总结中仍有效的信息。
- 将新的会话内容合并进总结，删除无关和重复内容。
- 输出简洁、客观、完整的总结。

EXAMPLE
当前总结:
Alice 和 Bob 在讨论晚餐计划，Alice 想吃意大利面，Bob 想吃寿司。

新的会话:
Human: 我其实也可以吃沙拉。
AI: 那我们可以把沙拉也加进选择里。

新的总结:
Alice 和 Bob 在讨论晚餐计划，他们考虑意大利面、寿司和沙拉作为晚餐选项。
END OF EXAMPLE

当前总结:
{summary}

新的会话:
{new_lines}

新的总结:
"""

# 会话名称提示词。标题本身是字符串，不要求模型使用工具或结构化输出。
CONVERSATION_NAME_TEMPLATE = """根据用户输入生成一个简短的会话标题。
要求：
- 使用与用户输入相同的主要语言。
- 不超过50个字符。
- 只输出标题，不要解释，不要添加“标题：”前缀，不要使用引号。"""


# 建议问题 提示词
SUGGESTED_QUESTIONS_TEMPLATE = "请根据历史信息预测人类最后可能会问的三个问题"


class SuggestedQuestions(BaseModel):
    """请预测人类最可能会问的三个问题，每个问题不超过50个字符。"""
    questions: list[str] = Field(description="建议问题列表，类型为字符串数组")


class InvokeFrom(str, Enum):
    """会话调用来源"""
    SERVICE_API = "service_api"  # 开放api服务调用
    WEB_APP = "web_app"  # web应用
    DEBUGGER = "debugger"  # 调试页面


class MessageStatus(str, Enum):
    """会话状态"""
    NORMAL = "normal"  # 正常
    STOP = "stop"  # 停止
    ERROR = "error"  # 出错
    TIMEOUT = "timeout"  # 超时
