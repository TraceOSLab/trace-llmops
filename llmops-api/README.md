# LLMOps API

Trace LLMOps 的后端服务。项目使用 Flask、SQLAlchemy、Celery、Redis、PostgreSQL 和 Weaviate；Python 依赖由 `uv` 管理。

## 本地开发

推荐直接用 VS Code 打开本目录 `llmops-api/`，不要只打开上一级仓库目录，否则 VS Code 不会自动加载这里的 `.vscode` 配置。

首次准备后端环境；如果本地还没有 `.env`，先从示例创建：

```bash
cp .env.example .env
uv sync --locked
```

真实配置和密钥只保存在本地 `.env`，不要提交到仓库。

返回仓库根目录；如果根目录还没有 `.env`，同样先从示例创建，然后启动 PostgreSQL、Redis 和 Weaviate：

```bash
cd ..
cp .env.example .env
docker compose up -d
```

随后在 VS Code 的 **Run and Debug** 中选择 `Development (Flask + Celery)` 并按 F5。该复合配置会同时启动可调试的 Flask API 和 Celery Worker；按 `⇧F5` 会一起停止二者。

如果当前工作不涉及异步任务，可以选择 `Flask API` 单独启动。数据库迁移和 Docker Compose 不会自动绑定到 F5，因为它们具有独立生命周期，并且迁移可能改变数据结构。

## 常用入口

- 完整的初始化、F5、Celery、数据库迁移和排障说明：[本地开发手册](../docs/runbooks/development.md)
- 系统组件和后端分层：[架构说明](../docs/architecture.md)
- Agent SSE 当前契约：[流式事件契约](../docs/contracts/agent-stream-events.md)
- Codex 在本仓库中的协作方式：[Codex 协作方式](../docs/codex-workflow.md)

## 终端备用方式

不使用 VS Code 调试器时，需要分别启动两个进程：

```bash
uv run flask --app app.http.app:create_app run --debug
uv run celery -A app.http.app:celery worker --loglevel=INFO --pool=solo
```

`--pool=solo` 用于本地开发和断点调试，不代表生产环境的并发部署方式。
