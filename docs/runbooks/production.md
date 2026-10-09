# 单服务器生产部署

从仓库根目录操作。服务器需要 Docker Engine 和 Docker Compose v2（`docker compose` 命令），不需要在宿主机安装 Python、uv、Node 或 pnpm。

## 容器如何协作

```mermaid
flowchart LR
    Browser[浏览器] --> TLS[服务器 HTTPS 入口]
    TLS --> Web[llmops-web:80 / Nginx]
    Web -->|/api 去掉前缀| API[llmops-api:5000 / Gunicorn]
    API --> PG[(postgres:5432)]
    API --> Redis[(redis:6379)]
    API --> WV[(weaviate:8080 / 50051)]
    Redis --> Worker[llmops-worker / Celery]
    Worker --> PG
    Worker --> WV
```

`compose.prod.yaml` 启动六个常驻服务。API 和 Worker 共用 `llmops-api/Dockerfile` 构建的镜像，但执行不同命令。容器通过服务名访问同一网络中的数据服务，因此容器里的 `localhost` 不能用来连接另一个容器。

只发布前端 `${WEB_BIND_IP:-0.0.0.0}:${WEB_PORT:-5173}`。API、PostgreSQL、Redis、Weaviate 不发布宿主机端口。浏览器访问 `/api/apps`，Nginx 转发成 API 的 `/apps`；Vue 页面仍由前端处理。默认使用同域 `/api`，无需填写服务器 IP，也无需因域名变化重建前端。更改 `WEB_API_BASE_URL` 本身则需要重新构建前端。

API 固定一个 Gunicorn 进程，默认八个 `gthread` 线程。当前 Agent Queue 是进程内对象，不能增加 API workers 或 replicas；并发 SSE 会占用线程，压力大时可以调整 `GUNICORN_THREADS`，但需实际压测。使用原生线程避免 gevent 对 gRPC、模型推理及已有线程代码的 monkey patch。Nginx 关闭响应缓冲，流式连接允许两次读取之间最多空闲 600 秒。线程行为和缓冲机制分别见 [Gunicorn 文档](https://docs.gunicorn.org/en/stable/design.html) 与 [Nginx 文档](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)。

## 1. 配置服务器 .env

本地和服务器使用同一份 `.env.example` 模板，各自在本机创建并配置 `.env`，不维护单独的生产模板。根目录模板用于 Compose，后端目录模板用于应用配置。

在服务器上拉取代码，进入仓库根目录。以下复制命令仅在文件还不存在时执行，避免覆盖现有密钥：

```bash
cp .env.example .env
cp llmops-api/.env.example llmops-api/.env
chmod 600 .env llmops-api/.env
```

用服务器编辑器分别填写两个文件，不要把它们提交到 Git。生成随机值可以执行 `openssl rand -hex 32`，每个密钥分别生成一次。

| 文件              | 必须填写/核对                                                                                                 | 用途                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 根目录 `.env`     | `PROJECT_NAME=trace-llmops`、`POSTGRES_USER=admin`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD`、`WEAVIATE_API_KEY` | Compose 镜像/容器/卷名称及三个数据服务的认证 |
| 根目录 `.env`     | `WEB_API_BASE_URL=/api`、`WEB_PORT=5173`、`WEB_BIND_IP=0.0.0.0`                                               | 前端构建地址和服务器 HTTP 入口；设置 HTTPS 代理后将绑定地址改成 `127.0.0.1`  |
| 根目录 `.env`     | `CELERY_CONCURRENCY=1` | 索引任务并发；先保持一个任务进程，避免重复加载模型占满内存 |
| `llmops-api/.env` | 生产开关、PostgreSQL URL、Redis 和 Weaviate 连接信息 | API/Worker 直接使用这里的值；数据服务凭证必须与根目录 `.env` 一致 |
| `llmops-api/.env` | 强随机 `JWT_SECRET_KEY`；所选模型的供应商密钥                                                                 | JWT 签名，以及对话/系统辅助任务所需的模型访问权限                            |
| `llmops-api/.env` | `SYSTEM_LLM_PROVIDER`、`SYSTEM_LLM_MODEL`                                                                     | 系统辅助任务模型；应用自己的模型仍由应用配置决定                             |
| `llmops-api/.env` | `COS_SECRET_ID`、`COS_SECRET_KEY`、`COS_REGION`、`COS_BUCKET`、`COS_DOMAIN`                                   | 上传、下载文档和图片所需的腾讯云对象存储；此 Compose 不会创建 COS 服务       |
| `llmops-api/.env` | 可选的 GitHub OAuth、搜索/地图工具密钥、`ASSISTANT_AGENT_ID`                                                  | 使用对应功能时填写；辅助 Agent ID 应替换为本环境中实际创建并发布的应用 UUID  |

`POSTGRES_PASSWORD` 会拼入数据库 URL，建议直接使用生成的十六进制值，避免 `@`、`/`、`#` 等字符需要额外 URL 编码。环境文件中的带 `$` 密钥应使用单引号包住，避免 Compose 插值。不要对密码使用行尾注释。

根目录 `.env` 负责 Compose 和数据服务配置，不会自动传给后端。API/Worker **只通过 `env_file` 加载 `llmops-api/.env`，没有 `environment` 覆盖**。服务器上把后端文件中的下列项改为：

```dotenv
FLASK_DEBUG=0
FLASK_ENV=production
SQLALCHEMY_ECHO=False
SQLALCHEMY_POOL_SIZE=10
SQLALCHEMY_DATABASE_URI=postgresql://admin:替换为根目录POSTGRES_PASSWORD@postgres:5432/llmops?client_encoding=utf8
REDIS_HOST=redis
REDIS_PASSWORD=替换为根目录REDIS_PASSWORD
WEAVIATE_HTTP_HOST=weaviate
WEAVIATE_GRPC_HOST=weaviate
WEAVIATE_API_KEY=替换为根目录WEAVIATE_API_KEY
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

数据库 URL 中的 `admin` 也要与根目录 `POSTGRES_USER` 一致。Redis 使用默认用户，保留 `REDIS_USERNAME=`、`REDIS_USE_SSL=False`；端口保持模板中的默认值。容器主机名使用 `postgres`、`redis`、`weaviate`，不能填 `localhost`。更改数据服务凭证时，两份 `.env` 必须同步修改。

默认禁用 LangSmith tracing；需要时自行填写并启用。使用自建模型网关时再设置 `OPENAI_API_BASE`，否则省略这个变量。不要把它设置成空字符串来表示默认端点。

后端模板的 `JWT_SECRET_KEY=dev-secret` 只供本地开发，服务器必须替换成随机值。模板仍只有一份，生产值在服务器 `.env` 中配置。

GitHub 的 `GITHUB_REDIRECT_URI` 和 OAuth App 的 callback 都应指向前端页面，例如 `https://llmops.example.com/auth/authorize/github`。该页面接收 code 后，再 POST 到 `/api/oauth/authorize/github`。不要把 callback 写成 API 的 POST 路由。

## 2. 构建并启动数据服务

```bash
docker compose -f compose.prod.yaml config --quiet
docker compose -f compose.prod.yaml build llmops-api llmops-web
docker compose -f compose.prod.yaml up -d --wait postgres redis weaviate
```

使用 `config --quiet`，避免将展开后的密钥打印到终端。镜像构建需要访问镜像仓库、Debian、PyPI 和 spaCy 模型的 GitHub 发布文件；构建也会缓存 tiktoken 数据，运行时无需首次联网下载 tokenizer。后端锁文件当前在 Linux x86_64 上还会安装 PyTorch CUDA 依赖，即使服务器只使用 CPU，镜像也较大；不要按普通 Flask 小镜像预估磁盘、构建时间和内存。API 和 Worker 会各自加载嵌入模型，应按实际服务器规格观察内存，再调整并发。

数据库数据沿用 `./volumes/postgres/data`，Redis 使用 `./volumes/redis/data`，Weaviate 使用 `./volumes/weaviate`。不要把开发数据库目录覆盖到这些目录。PostgreSQL 的 UUID 扩展初始化文件现在挂载到正确的 `docker-entrypoint-initdb.d` 目录，只在首次空库初始化时执行；已有数据目录不会重新执行它。已有迁移使用 `uuid_generate_v4()`，但不创建扩展，因此迁移前再显式检查/创建扩展。

## 3. 下载本地嵌入模型

首次部署在启动索引任务前执行；这两条命令只下载开源模型，不调用付费 LLM：

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

模型保存在共享命名卷 `embeddings_cache`，API 和 Worker 均挂载到代码实际使用的 `/app/internal/core/embeddings`。下载命令必须成功完成。若服务器不能访问 Hugging Face，先在可联网环境下载同样的完整 Hugging Face 缓存结构（包含 snapshots、blobs 及自定义实现），再导入该卷；不能只复制模型权重文件。

运行期设置 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1`，不会自动补下载。首次检索会加载模型，需要等待。OCR/Office 系统工具已安装，但扫描 PDF 等解析路径可能另外需要 Unstructured 模型资源，不能把容器启动成功当成所有文件格式均可离线解析；上线前用真实样本文档做索引与检索检查。

## 4. 迁移数据库并启动应用

```bash
docker compose -f compose.prod.yaml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d llmops -v ON_ERROR_STOP=1' <<'SQL'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SQL

docker compose -f compose.prod.yaml run --rm --no-deps \
  llmops-api flask --app app.http.app:create_app db upgrade

docker compose -f compose.prod.yaml up -d --wait
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs --tail=100 llmops-api llmops-worker llmops-web
```

迁移失败时先解决错误再启动应用，不要继续下一条命令。迁移采用当前仓库的已有历史，不在 API 与 Worker 的公共启动命令中自动执行，以免多个容器竞争修改数据库。启动后 Worker 日志应出现 `ready`，注册的任务列表应包括文档任务与应用任务。

未配置域名时，可临时访问 `http://服务器IP:5173`（云安全组需允许此端口）。检查前端与代理：

```bash
curl -fsS http://127.0.0.1:5173/healthz
curl -fsS http://127.0.0.1:5173/api/apps
```

第一条应返回 `ok`；第二条不带 Token，应返回 JSON 的 `code: unauthorized`。后者检查真实 Flask 路由与鉴权链路，不会调用模型。**不要拿 `/ping` 做健康检查：它是会调用模型的演示接口。** API 的容器健康检查也采用无 Token 的 `/apps`，不代表数据库 Schema、模型、COS 和业务链路全部可用。

接着在网页完成登录、创建应用、流式聊天与停止、文档上传及索引检索。HTTP 200 不代表业务成功，还应检查 JSON 的 `code`、SSE 终止事件、Worker 日志和索引状态；模型调用在这个阶段由你主动发起并可能产生费用。已有账号和业务数据不会由 Compose 自动创建。

## 5. 配置域名和 HTTPS

容器内 Nginx 提供 HTTP。正式对外使用时将域名解析到服务器，在宿主机已有 Nginx/网关上配置 TLS 证书，把整个站点转发到本机前端端口。根目录 `.env` 改成 `WEB_BIND_IP=127.0.0.1`，保留 `WEB_PORT=5173`，然后重新创建前端容器：

```bash
docker compose -f compose.prod.yaml up -d llmops-web
```

外层 Nginx 的已配置证书的 HTTPS `server` 中可使用：

```nginx
client_max_body_size 20m;
location / {
    proxy_pass http://127.0.0.1:5173;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}
```

外层入口也必须关闭 SSE 缓冲并允许上传体积，否则内层配置不会消除外层的限制。检查宿主机 Nginx 配置后再重载。云安全组最终保留站点 80/443 与管理所需端口，不开放数据库、Redis 或 Weaviate 端口。

## 更新、停止和数据保留

调整后端环境文件后，执行下面命令重新创建进程；单独 `restart` 不会更新容器环境变量：

```bash
docker compose -f compose.prod.yaml up -d --force-recreate llmops-api llmops-worker
```

升级代码前备份 PostgreSQL、Weaviate 和对象存储数据，然后构建镜像。若包含迁移，安排维护窗口，停止应用入口/任务，运行一次迁移后再启动：

```bash
docker compose -f compose.prod.yaml build llmops-api llmops-web
docker compose -f compose.prod.yaml stop llmops-web llmops-api llmops-worker
docker compose -f compose.prod.yaml run --rm --no-deps \
  llmops-api flask --app app.http.app:create_app db upgrade
docker compose -f compose.prod.yaml up -d --wait
```

前端 Nginx 使用 Docker DNS 动态解析 API 地址，API 重建更换容器 IP 后会重新解析。正在进行的 SSE 会在重启时断开，当前应用不支持重放，不要自动重发消息。

停止所有容器但保留数据：`docker compose -f compose.prod.yaml down`。不要加 `-v`，它会删除模型与日志命名卷；也不要删除 `volumes/`。`api_storage` 保留后端文件日志与 Hugging Face 自定义代码缓存；应用文件日志可用 `docker compose -f compose.prod.yaml exec llmops-api tail -n 100 storage/log/app.log` 查看。Gunicorn/Celery 进程日志则使用 `docker compose logs`。

环境文件、`PROJECT_NAME`、数据目录与卷属于部署状态，更新代码时应保留。更改数据库环境变量不会自动更改已初始化 PostgreSQL 的账号/密码；改名也会改变 Compose 命名卷名称。已有数据的凭证轮换或迁移应单独安排。
