"""Weaviate 配置、注入和上下文生命周期；不加载模型或访问任何外部服务。"""

import importlib.util
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import flask_weaviate
import pytest
from flask import Flask
from flask_weaviate import FlaskWeaviate

from config import Config


API_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("此测试禁止网络访问")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture
def vector_module(monkeypatch):
    # 仅隔离 EmbeddingsService 的重型模型依赖，加载真实的向量服务源码。
    package = ModuleType("_weaviate_test_services")
    package.__path__ = []
    embeddings_module = ModuleType(f"{package.__name__}.embeddings_service")
    embeddings_module.EmbeddingsService = type("EmbeddingsService", (), {})
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setitem(sys.modules, embeddings_module.__name__, embeddings_module)
    name = f"{package.__name__}.vector_database_service"
    spec = importlib.util.spec_from_file_location(
        name, API_ROOT / "internal/service/vector_database_service.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clients(monkeypatch, vector_module):
    created = []

    class Client:
        def __init__(self, **kwargs):
            self.config = kwargs
            self.connected = False
            self.close_count = 0
            self.collections = SimpleNamespace(get=lambda name: (self, name))
            created.append(self)

        def is_connected(self):
            return self.connected

        def connect(self):
            self.connected = True

        def close(self):
            self.close_count += 1
            self.connected = False

    class VectorStore:
        def __init__(self, client, **kwargs):
            assert client.is_connected()
            self.client = client
            self.config = kwargs

    monkeypatch.setattr(flask_weaviate, "WeaviateClient", Client)
    monkeypatch.setattr(vector_module, "WeaviateVectorStore", VectorStore)
    return created


@pytest.fixture
def conf(monkeypatch):
    monkeypatch.setenv("WEAVIATE_HTTP_HOST", "http.internal")
    monkeypatch.setenv("WEAVIATE_HTTP_PORT", "8088")
    monkeypatch.setenv("WEAVIATE_GRPC_HOST", "grpc.internal")
    monkeypatch.setenv("WEAVIATE_GRPC_PORT", "50058")
    monkeypatch.setenv("WEAVIATE_API_KEY", " ")
    return Config()


@pytest.fixture
def runtime(conf, vector_module, clients):
    app = Flask(__name__)
    app.config.from_object(conf)
    extension = FlaskWeaviate()
    extension.init_app(app)
    service = vector_module.VectorDatabaseService(
        embeddings_service=SimpleNamespace(embeddings=object()), weaviate=extension
    )
    return app, service


@pytest.mark.parametrize("api_key", ["", " ", " local-test-key "])
def test_config_reaches_extension_client(monkeypatch, conf, clients, api_key):
    monkeypatch.setenv("WEAVIATE_API_KEY", api_key)
    conf = Config()
    assert type(conf.WEAVIATE_HTTP_PORT) is int
    assert type(conf.WEAVIATE_GRPC_PORT) is int
    app = Flask(__name__)
    app.config.from_object(conf)
    extension = FlaskWeaviate()
    extension.init_app(app)
    assert clients == []  # 初始化扩展不建立连接。
    with app.app_context():
        client = extension.client
        params = client.config["connection_params"]
        assert (params.http.host, params.http.port) == ("http.internal", 8088)
        assert (params.grpc.host, params.grpc.port) == ("grpc.internal", 50058)
        assert client.config["embedded_options"] is None
        auth = client.config["auth_client_secret"]
        if api_key.strip():
            assert auth.api_key == "local-test-key"
        else:
            assert auth is None
    assert client.close_count == 1


def test_injector_supplies_registered_extension(vector_module, clients):
    from app.http.module import ExtensionModule
    from injector import Injector
    from internal.extension.weaviate_extension import weaviate

    injector = Injector([ExtensionModule])
    injector.binder.bind(
        vector_module.EmbeddingsService, to=SimpleNamespace(embeddings=object())
    )
    service = injector.get(vector_module.VectorDatabaseService)
    assert service.weaviate is weaviate
    assert clients == []


def test_context_reuses_store_but_next_context_gets_new_client(runtime, clients):
    app, service = runtime
    with app.app_context():
        assert clients == []
        first = service.vector_store
        assert service.vector_store is first
        assert service.client is first.client
        assert service.collection == (first.client, "Dataset")
        assert first.config["embedding"] is service.embeddings_service.embeddings
    assert first.client.close_count == 1
    with app.app_context():
        second = service.vector_store
        assert second is not first
        assert second.client is not first.client
        assert second.client.is_connected()
    assert second.client.close_count == 1


def test_nested_context_does_not_close_outer_client(runtime):
    app, service = runtime
    with app.app_context():
        outer = service.vector_store
        with app.app_context():
            inner = service.vector_store
            assert inner.client is not outer.client
        assert inner.client.close_count == 1
        assert outer.client.is_connected()
        assert service.vector_store is outer
    assert outer.client.close_count == 1


def test_indexing_threads_own_independent_clients(runtime):
    app, service = runtime
    ready = Barrier(2, timeout=5)
    first_closed = Event()

    def worker(first):
        with app.app_context():
            store = service.vector_store
            ready.wait()
            if not first:
                assert first_closed.wait(timeout=5)
                assert store.client.is_connected()
        if first:
            first_closed.set()
        return store

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker, first) for first in (True, False)]
        stores = [future.result(timeout=10) for future in futures]
    assert stores[0].client is not stores[1].client
    assert [store.client.close_count for store in stores] == [1, 1]


@pytest.mark.parametrize("failure", ["connect", "store"])
def test_initialization_failure_still_closes_client(
    runtime, clients, vector_module, monkeypatch, failure
):
    app, service = runtime
    if failure == "connect":
        monkeypatch.setattr(
            flask_weaviate.WeaviateClient, "connect", Mock(side_effect=RuntimeError("failed"))
        )
    else:
        monkeypatch.setattr(
            vector_module, "WeaviateVectorStore", Mock(side_effect=RuntimeError("failed"))
        )
    with pytest.raises(RuntimeError, match="failed"), app.app_context():
        service.vector_store
    assert len(clients) == 1
    assert clients[0].close_count == 1


def test_http_initializes_extension_and_closes_each_request(
    conf, vector_module, clients, monkeypatch
):
    # 隔离 Router/Middleware 的业务依赖，实际执行 Http 的扩展初始化路径。
    for name, attribute in [("internal.router", "Router"), ("internal.middleware", "Middleware")]:
        stub = ModuleType(name)
        setattr(stub, attribute, type(attribute, (), {}))
        monkeypatch.setitem(sys.modules, name, stub)
    spec = importlib.util.spec_from_file_location(
        "_weaviate_test_http", API_ROOT / "internal/server/http.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for extension in [module.redis_extension, module.celery_extension, module.logging_extension]:
        monkeypatch.setattr(extension, "init_app", lambda app: None)
    extension = FlaskWeaviate()
    monkeypatch.setattr(module, "weaviate", extension)
    service = vector_module.VectorDatabaseService(SimpleNamespace(embeddings=object()), extension)

    def register(app):
        def view():
            service.vector_store
            return "ok"
        app.add_url_rule("/vector", view_func=view)

    app = module.Http(
        __name__, conf=conf, router=SimpleNamespace(register_router=register),
        db=Mock(), migrate=Mock(), login_manager=Mock(), middleware=Mock(),
    )
    assert app.extensions["weaviate"] is extension
    assert clients == []
    client = app.test_client()
    for _ in range(2):
        assert client.get("/vector").status_code == 200
    assert len(clients) == 2
    assert [client.close_count for client in clients] == [1, 1]


@pytest.mark.parametrize("fail", [False, True])
def test_celery_context_closes_client_on_success_and_failure(runtime, clients, fail):
    from celery import current_app
    from internal.extension.celery_extension import init_app

    app, service = runtime
    previous = current_app._get_current_object()
    app.config["CELERY"] = {"broker_url": "memory://", "task_ignore_result": True}
    init_app(app)
    celery = app.extensions["celery"]

    @celery.task
    def use_vector_store():
        service.vector_store
        if fail:
            raise RuntimeError("index failed")

    try:
        if fail:
            with pytest.raises(RuntimeError, match="index failed"):
                use_vector_store.apply(throw=True)
        else:
            use_vector_store.apply(throw=True)
        assert len(clients) == 1
        assert clients[0].close_count == 1
    finally:
        celery.close()
        previous.set_default()
