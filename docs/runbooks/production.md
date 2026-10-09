# 单服务器生产部署：Flask API 与 Celery

从仓库根目录操作，服务器需要 Docker Engine 和 Docker Compose v2。当前阶段完成 API、Celery 以及现有前端静态镜像的构建与启动，不配置 Nginx API 反向代理、域名或 SSL。

## 服务与配置位置

`compose.prod.yaml` 包含 `llmops-web`、`llmops-api`、`llmops-celery`、`postgres`、`redis`、`weaviate`。API 与 Celery 使用同一个 `llmops-api/Dockerfile` 和 `docker/entrypoint.sh`，由环境变量 `MODE` 选择进程。入口使用 `exec`，容器停止信号能传给 Gunicorn/Celery。

| 文件 | 用途 |
| --- | --- |
| 根目录 `.env` | Compose 插值：项目名、数据服务凭证、前端构建时 API 地址 |
| `llmops-api/.env` | API/Celery 通过 `env_file` 读取的公共应用配置，默认 `MODE=api` |
| `llmops-api/.env.celery` | Celery 后加载的覆盖文件：`MODE=celery`、并发和日志级别 |

API/Celery 的 Compose 配置没有 `environment`。数据服务沿用已有配置。Celery 覆盖文件只保存与进程有关的差异，数据库、Redis、模型供应商等公共设置仍只维护一份。

API 暂时发布 `5001:5001`，前端发布 `5173:80`。数据库、Redis、Weaviate 通过内部服务名访问，不发布宿主机端口。当前前端 Nginx 仅提供静态文件，因此浏览器直接访问 API 地址；`WEB_API_BASE_URL` 必须是浏览器可达的 `http://服务器IP:5001`，不能填 Docker 内部的 `llmops-api`，也不能用服务器的 `localhost`。

Vite 在构建时把 API 地址写进 JavaScript，给前端容器添加运行时 `env_file` 不会改变它。因此前端继续用根目录 `.env` 中的 `WEB_API_BASE_URL` 传入构建参数；更改地址后必须重建前端镜像。

## 1. 在服务器编写环境文件

模板仅供参考；自行在服务器编写文件，不要提交密钥。如果文件还不存在，可复制：

```bash
cp .env.example .env
cp llmops-api/.env.example llmops-api/.env
cp llmops-api/.env.celery.example llmops-api/.env.celery
chmod 600 .env llmops-api/.env llmops-api/.env.celery
```

根目录 `.env` 填写 `PROJECT_NAME`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD`、`WEAVIATE_API_KEY` 与 `WEB_API_BASE_URL`。后端 `.env` 配齐 JWT、COS、所选模型供应商等业务配置，并改为：

```dotenv
FLASK_ENV=production
FLASK_DEBUG=0
MODE=api
MIGRATION_ENABLED=false
LLMOPS_BIND_ADDRESS=0.0.0.0
LLMOPS_PORT=5001
SERVER_WORKER_AMOUNT=1
SERVER_WORKER_CLASS=gthread
SERVER_THREAD_AMOUNT=8
GUNICORN_TIMEOUT=600
SQLALCHEMY_ECHO=False
SQLALCHEMY_DATABASE_URI=postgresql://admin:替换为数据库密码@postgres:5432/llmops?client_encoding=utf8
REDIS_HOST=redis
REDIS_PASSWORD=替换为Redis密码
WEAVIATE_HTTP_HOST=weaviate
WEAVIATE_GRPC_HOST=weaviate
WEAVIATE_API_KEY=替换为Weaviate密钥
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
LANGSMITH_TRACING=false
```

数据库 URL 中的用户名和密码，以及 Redis/Weaviate 凭证，必须与根目录 `.env` 一致。数据库密码若含 URL 特殊字符，需要 URL 编码；可使用 `openssl rand -hex 32` 生成无此问题的随机值。JWT 必须替换开发模板中的 `dev-secret`。无需自建 OpenAI 网关时，删掉空的 `OPENAI_API_BASE` 配置。

服务器 `llmops-api/.env.celery` 使用：

```dotenv
MODE=celery
MIGRATION_ENABLED=false
CELERY_WORKER_CLASS=prefork
CELERY_WORKER_AMOUNT=1
CELERY_LOG_LEVEL=INFO
```

API 保持一个 Gunicorn worker：现有 Agent/SSE 队列在进程内，不支持多 API 进程共享。并发请求由 `gthread` 线程处理。Celery 从一个 prefork 子进程开始，避免多份嵌入模型占用过多内存。修改 `LLMOPS_PORT` 时也要同步 Compose 端口映射和前端构建地址。

Celery 的 `broker_url` 和 `result_backend` 使用 `REDIS_USERNAME`、`REDIS_PASSWORD` 构造认证信息，并对 URL 中的凭证进行编码。当前 Compose 的 Redis 使用默认用户密码认证，保持 `REDIS_USERNAME=` 即可；只有在 Redis 中配置了命名 ACL 用户时才填写对应用户名。用户名和密码均为空时，URL 不包含认证信息。

## 2. 构建并启动数据服务

```bash
docker compose -f compose.prod.yaml config --quiet
docker compose -f compose.prod.yaml build llmops-api llmops-web
docker compose -f compose.prod.yaml up -d postgres redis weaviate
docker compose -f compose.prod.yaml ps
```

API/Celery 等待 PostgreSQL 和 Redis 健康检查通过；Weaviate 目前只等待容器启动，不代表其就绪。构建需要下载基础镜像、系统包和锁文件中的 Python/Node 依赖。后端按 `uv.lock` 安装，Linux x86_64 上的 PyTorch CUDA 依赖会使镜像较大。

数据库沿用 `./volumes/postgres/data`，Redis 使用 `./volumes/redis/data`，Weaviate 使用 `./volumes/weaviate`。API/Celery 共享 `api_storage` 日志/缓存卷和 `embeddings_cache` 模型卷。后端以 UID/GID `10001` 的非 root 用户运行；如果导入已有卷，需保证这两个应用卷对该用户可写。

## 3. 准备嵌入模型并迁移数据库

现有 EmbeddingsService 只加载本地模型。首次索引前下载完整模型缓存；以下命令不调用付费模型：

```bash
docker compose -f compose.prod.yaml run --rm --no-deps \
  -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 \
  llmops-api hf download Alibaba-NLP/gte-multilingual-base \
  --cache-dir /app/internal/core/embeddings

docker compose -f compose.prod.yaml run --rm --no-deps \
  -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 \
  llmops-api hf download Alibaba-NLP/new-impl \
  --cache-dir /app/internal/core/embeddings
```

无法联网时，将完整 Hugging Face 缓存导入同一卷，包括 snapshots、blobs 和自定义实现。Dockerfile 安装了 PDF/OCR/Office 系统工具，但 tiktoken、NLTK 或 Unstructured 仍可能首次下载资源，不能将容器启动成功当成所有文档格式均已验证。

PostgreSQL 空库初始化会执行 `docker/postgres/init.sql`；已有数据库不会重跑初始化脚本。数据库就绪后确认 UUID 扩展，再执行一次迁移：

```bash
docker compose -f compose.prod.yaml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d llmops -v ON_ERROR_STOP=1' <<'SQL'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SQL

docker compose -f compose.prod.yaml run --rm --no-deps \
  llmops-api flask --app app.http.app:create_app db upgrade
```

迁移失败先解决错误，再启动应用。`MIGRATION_ENABLED` 默认关闭，建议使用一次性命令；设为 `true` 只让 API 启动时迁移，Celery 不迁移。

## 4. 启动和检查应用

```bash
docker compose -f compose.prod.yaml up -d llmops-api llmops-celery llmops-web
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs --tail=100 llmops-api llmops-celery
curl -fsS http://127.0.0.1:5001/apps
```

无 Token 的 `/apps` 应返回鉴权失败 JSON，用于检查 HTTP 与鉴权链路；不验证数据库 Schema、模型或业务成功。不要使用会调用模型的 `/ping`。Celery 日志应出现 `ready` 和注册的任务。

浏览器访问 `http://服务器IP:5173`，当前阶段需要服务器允许前端 `5173` 和 API `5001` 端口。登录、流式聊天、停止任务、文档索引需要随后进行真实业务验证，模型调用可能产生费用。Nginx 代理与 SSL 留待后续配置。

## 更新和数据保留

修改环境文件后重新创建 API/Celery，单独 `restart` 不会加载新配置：

```bash
docker compose -f compose.prod.yaml up -d --force-recreate llmops-api llmops-celery
```

代码更新后重建镜像；如果有数据库迁移，先备份并停止应用，执行一次迁移，再启动。前端地址变更也要重建前端镜像。

`docker compose -f compose.prod.yaml down` 停止容器并保留数据。不要加 `-v`，否则会删除应用日志与模型缓存卷；也不要删除 `volumes/`。本地环境文件和已有数据目录属于服务器部署状态，更新代码时保留。
