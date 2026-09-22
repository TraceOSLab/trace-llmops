from dataclasses import dataclass

from injector import inject
from werkzeug.exceptions import FailedDependency

from internal.entity.app_entity import AppStatus
from internal.exception.exception import FailException
from internal.model.account import Account
from internal.model.app import App

from .base_service import BaseService


@inject
@dataclass
class WebAppService(BaseService):
    """Webapp 服务"""

    def get_web_app(self, token: str) -> App:
        """根据TOKEN获取应用"""
        app = self.db.session.query(App).filter(App.token == token).one_or_none()
        if not app:
            raise FailException("该应用不存在")
        if app.status != AppStatus.PUBLISHED:
            raise FailedDependency("该应用未发布")

        return app
