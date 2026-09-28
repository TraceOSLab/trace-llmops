#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   logging_extension
@Time   :   2025/12/16 13:39
@Author :   s.qiu@foxmail.com
"""

import logging
import os
from concurrent_log_handler import ConcurrentRotatingFileHandler


def init_app(app):
    """日志记录器"""

    # 根据不同环境设置日志级别
    logging.getLogger().setLevel(
        logging.DEBUG
        if app.debug or os.getenv("FLASK_ENV") == "development"
        else logging.WARNING
    )

    # 日志储存的位置
    log_folder = os.path.join(os.getcwd(), "storage", "log")
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)
    log_file = os.path.join(log_folder, "app.log")

    # 每天更新一次日志
    handler = ConcurrentRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] %(filename)s -> %(funcName)s line:%(lineno)d [%(levelname)s]: %(message)s"
    )
    handler.setLevel(
        logging.DEBUG
        if app.debug or os.getenv("FLASK_ENV") == "development"
        else logging.WARNING
    )
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

    # 在开发环境下同时将日志输出到控制台
    if app.debug or os.getenv("FLASK_ENV") == "development":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)
