from dataclasses import dataclass

from flask_login import login_required
from injector import inject

from internal.schema.web_app_schema import GetWebAppResp
from internal.service import WebAppService
from pkg.response.response import success_json


@inject
@dataclass
class WebAppHandler:
    """Webapp 处理器"""

    web_app_service: WebAppService

    @login_required
    def get_web_app(self, token: str):
        """根据TOKEN获取应用"""
        app = self.web_app_service.get_web_app(token)
        resp = GetWebAppResp()
        return success_json(resp.dump(app))
