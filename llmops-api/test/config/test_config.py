"""离线检查 Celery Redis URL 的认证和数据库配置。"""

import pytest
from kombu.utils.url import parse_url
from redis import ConnectionPool

from config import Config


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("", ""),
        ("", "test-password"),
        ("worker", "test-password"),
        ("worker@team:/%", "p@ss:/?#%+ 密码"),
    ],
)
def test_celery_redis_credentials(monkeypatch, username, password):
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_USERNAME", username)
    monkeypatch.setenv("REDIS_PASSWORD", password)
    monkeypatch.setenv("CELERY_BROKER_DB", "1")
    monkeypatch.setenv("CELERY_RESULT_BACKEND_DB", "2")
    config = Config()

    for key, db in [("broker_url", 1), ("result_backend", 2)]:
        url = config.CELERY[key]
        # 两种客户端解析 URL，但不建立连接。
        broker = parse_url(url)
        pool = ConnectionPool.from_url(url)
        options = pool.connection_kwargs
        assert broker["hostname"] == options["host"] == "redis"
        assert broker["port"] == options["port"] == 6379
        assert broker["userid"] == (username or None)
        assert broker["password"] == (password or None)
        assert options.get("username") == (username or None)
        assert options.get("password") == (password or None)
        assert broker["virtual_host"] == str(db)
        assert options["db"] == db
