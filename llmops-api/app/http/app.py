#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File   :   app
@Time   :   2025/9/1 13:59
@Author :   s.qiu@foxmail.com
"""
import dotenv
from flask_login import LoginManager
from flask_migrate import Migrate

from config import Config
from internal.middleware import Middleware
from internal.router import Router
from internal.server import Http
from pkg.sqlalchemy import SQLAlchemy
from .module import injector

# 加载ENV到环境变量
dotenv.load_dotenv()

# 加载配置
conf = Config()

_app: Http | None = None


def create_app() -> Http:
    """Flask 工厂函数，延迟解析依赖注入链"""
    global _app
    if _app is not None:
        return _app
    _app = Http(
        __name__,
        conf=conf,
        db=injector.get(SQLAlchemy),
        migrate=injector.get(Migrate),
        middleware=injector.get(Middleware),
        login_manager=injector.get(LoginManager),
        router=injector.get(Router),
    )
    return _app


# 模块级 app 变量供非 CLI 场景使用（test/conftest.py 等）
# Flask CLI 优先使用 create_app() 工厂函数
app = create_app()

celery = app.extensions["celery"]

if __name__ == "__main__":
    app.run(debug=True)
