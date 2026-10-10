# 单服务器生产部署：Nginx、前端、Flask API 与 Celery

从仓库根目录操作，服务器需要 Docker Engine 和 Docker Compose v2。入口 Nginx 通过 `https://llmops.qiuyouyou.cn` 提供前端与 API，HTTP 80 自动重定向到 HTTPS 443。

## 服务与配置位置

`compose.prod.yaml` 包含 `llmops-nginx`、`llmops-web`、`llmops-api`、`llmops-celery`、`postgres`、`redis`、`weaviate`。API 与 Celery 使用同一个 `llmops-api/Dockerfile` 和 `docker/entrypoint.sh`，由环境变量 `MODE` 选择进程。入口使用 `exec`，容器停止信号能传给 Gunicorn/Celery。

| 文件 | 用途 |
| --- | --- |
| 根目录 `.env` | Compose 插值：项目名、数据服务凭证 |
| `llmops-api/.env` | API/Celery 通过 `env_file` 读取的公共应用配置，默认 `MODE=api` |
| `llmops-api/.env.celery` | Celery 后加载的覆盖文件：`MODE=celery`、并发和日志级别 |
| `nginx/nginx.conf` | 入口 Nginx 主配置与 Docker DNS |
| `nginx/proxy.conf` | 通用代理请求头和超时 |
| `nginx/conf.d/default.conf` | `/` 与 `/api/` 分流、SSE 和上传配置 |
| `nginx/ssl/` | 服务器单独上传的域名证书链和私钥，只读挂载，不提交 Git |

API/Celery 的 Compose 配置没有 `environment`。数据服务沿用已有配置。Celery 覆盖文件只保存与进程有关的差异，数据库、Redis、模型供应商等公共设置仍只维护一份。

只有入口 Nginx 发布宿主机 `80:80` 和 `443:443`，80 使用 308 重定向到固定域名的 HTTPS 地址，保留请求方法、路径和查询参数。HTTPS 的 `/` 转发到 `llmops-web:3000`，前端容器内的 Nginx 提供静态文件与 Vue 路由回退；`/api/` 转发到 `llmops-api:5001`，去掉 `/api/` 前缀，例如 `/api/apps` 到达 Flask 时为 `/apps`。TLS 在入口 Nginx 终止，内部代理继续使用 HTTP，并通过 `X-Forwarded-Proto: https` 传递入口协议。API、前端和数据服务均不发布宿主机端口。

Compose 将前端构建参数 `WEB_API_BASE_URL` 固定为 `/api`，浏览器通过同一地址访问页面和 API。服务器根目录 `.env` 中旧的 `WEB_API_BASE_URL` 已不参与生产构建，可删除。Vite 在构建时写入这个地址，升级到本配置时必须重建前端镜像。

API 代理关闭响应缓冲和压缩，保留 SSE 逐段传输；读取超时为相邻两次上游读取之间的 600 秒，不是整个会话时长。上传请求上限为 20 MiB，为后端 15 MiB 文件限制留出 multipart 开销。上游使用 Docker DNS 动态解析，重建 API/前端容器后会刷新地址。动态解析配置要求 Nginx 1.27.3 或更新版本，入口使用 `nginx:stable-alpine`。

## 1. 在服务器编写环境文件

模板仅供参考；自行在服务器编写文件，不要提交密钥。如果文件还不存在，可复制：

```bash
cp .env.example .env
cp llmops-api/.env.example llmops-api/.env
cp llmops-api/.env.celery.example llmops-api/.env.celery
chmod 600 .env llmops-api/.env llmops-api/.env.celery
```

根目录 `.env` 填写 `PROJECT_NAME`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD`、`WEAVIATE_API_KEY`。后端 `.env` 配齐 JWT、COS、所选模型供应商等业务配置，并改为：

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

API 保持一个 Gunicorn worker：现有 Agent/SSE 队列在进程内，不支持多 API 进程共享。并发请求由 `gthread` 线程处理。Celery 从一个 prefork 子进程开始，避免多份嵌入模型占用过多内存。修改 `LLMOPS_PORT` 时也要同步 Compose 的 `expose` 和 `nginx/conf.d/default.conf` 中的 API 上游端口。

Celery 的 `broker_url` 和 `result_backend` 使用 `REDIS_USERNAME`、`REDIS_PASSWORD` 构造认证信息，并对 URL 中的凭证进行编码。当前 Compose 的 Redis 使用默认用户密码认证，保持 `REDIS_USERNAME=` 即可；只有在 Redis 中配置了命名 ACL 用户时才填写对应用户名。用户名和密码均为空时，URL 不包含认证信息。

## 2. 构建并启动数据服务

### 下载镜像源

项目已分别配置以下来源；APT、Python 包、Node 包和 Docker 镜像是独立的下载链路，设置其中一种不会加速其他下载。

| 下载内容 | 配置位置与来源 |
| --- | --- |
| Python 包 | `llmops-api/pyproject.toml` 默认清华 PyPI；`uv.lock` 的包下载地址也已切换 |
| uv 工具 | 后端 Dockerfile 通过清华 PyPI 安装固定 `uv==0.12.5`，不再拉取 GHCR 的 uv 镜像 |
| Debian 系统包 | 后端 Dockerfile 的构建与运行阶段均使用清华 Debian 镜像 |
| npm/pnpm 包与 pnpm 工具 | 前端 Dockerfile 的 `npm_config_registry` 与根目录 `pnpm-workspace.yaml` 的 `registry` 均设置为腾讯云 npm 镜像 |
| Docker Hub 镜像 | 腾讯云服务器使用 `docker/daemon.json.example` 中的内网加速地址 |
| Hugging Face 模型 | 后端镜像设置 `HF_ENDPOINT=https://hf-mirror.com`，仍需显式关闭离线模式后下载模型 |
| spaCy `en-core-web-sm` 模型 wheel | 保留固定版本的 GitHub 官方下载地址与 SHA256；PyPI 镜像不会代理这个 URL |

uv 锁文件保留原有 254 条包版本记录和所有发行文件 SHA256。`--frozen` 直接使用新的镜像下载地址；不要手工只替换版本或校验值。后端 uv 与 pip 使用 BuildKit 缓存挂载，依赖层重新构建时可复用已下载的包。缓存不能减少首次所需的下载量；PyTorch/CUDA 依赖目前保留原配置。

在腾讯云服务器上首次配置 Docker 加速时，从仓库根目录执行：

```bash
sudo python3 scripts/configure-docker-mirror.py
sudo dockerd --validate --config-file /etc/docker/daemon.json
sudo systemctl restart docker
sudo sh scripts/pull-production-images.sh
```

配置脚本将镜像地址合并到服务器 `/etc/docker/daemon.json`，保留原有其他配置和镜像地址，修改前生成权限为 `600` 的备份；再次执行不会重复添加。修改镜像地址只需编辑 `docker/daemon.json.example`。Docker 重启会影响已有容器，应在首次构建前或维护时执行。脚本没有被应用到开发电脑或远程服务器，需在服务器执行以上命令。

预拉取脚本从 Compose 与两个 Dockerfile 读取镜像名称和版本，通过腾讯云内网代理拉取并保留原标签；其中包括 Weaviate 的 `cr.weaviate.io` 标签。API/web 的本地构建标签会跳过，任何拉取失败都会停止。此步骤也避免显式指定 `cr.weaviate.io` 的镜像绕过 Docker Hub 加速配置。内网地址只适用于腾讯云服务器，不要配置到普通本地电脑。

默认 Docker builder 使用 Docker Engine 的镜像设置；自行创建的 `docker-container` BuildKit builder 还需单独配置 registry mirror。模型镜像不会代理 GitHub、tiktoken、NLTK 或 Unstructured 内置下载地址。spaCy 官方 wheel 如果下载超时，可在可联网的机器构建镜像后导入服务器，或使用已准备好的构建缓存。

镜像地址依据 [清华 PyPI 说明](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)、[腾讯云软件源说明](https://cloud.tencent.com/document/product/213/8623) 与 [HF-Mirror 使用说明](https://hf-mirror.com/) 配置；Docker Hub 加速的范围见 [Docker 文档](https://docs.docker.com/docker-hub/image-library/mirror/)。实际下载速度以服务器网络为准。

### 构建与启动

```bash
docker compose -f compose.prod.yaml config --quiet
docker compose -f compose.prod.yaml build llmops-api llmops-web
docker compose -f compose.prod.yaml up -d postgres redis weaviate
docker compose -f compose.prod.yaml ps
```

API/Celery 等待 PostgreSQL 和 Redis 健康检查通过；Weaviate 目前只等待容器启动，不代表其就绪。构建需要下载基础镜像、系统包和锁文件中的 Python/Node 依赖。后端按 `uv.lock` 安装，Linux x86_64 上的 PyTorch CUDA 依赖会使镜像较大。

后端 Dockerfile 在构建阶段和运行阶段的 `apt-get update` 前，将 Debian 普通源和安全更新源切换到清华镜像，保留 Bookworm 套件和签名校验配置，不修改宿主机 APT 源。正在运行的构建不会自动加载修改；更新服务器上的 Dockerfile、`pyproject.toml` 和 `uv.lock` 后停止原构建，再执行上面的 build 命令，无需添加 `--no-cache`。前端 Dockerfile 的 npm 镜像变更也需要重新构建前端。

数据库沿用 `./volumes/postgres/data`，Redis 使用 `./volumes/redis/data`，Weaviate 使用 `./volumes/weaviate`。API/Celery 共享宿主机 `./volumes/app/storage` 日志/缓存目录和 `./volumes/app/embeddings` 模型目录。后端以 UID/GID `10001` 的非 root 用户运行；首次部署在运行应用命令前创建可写目录：

```bash
sudo install -d -m 0755 -o 10001 -g 10001 volumes/app/storage volumes/app/embeddings
```

如果导入已有数据，需保证这两个目录中的文件也对该用户可读写。

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

## 4. 配置域名与 HTTPS 证书

将域名 `llmops.qiuyouyou.cn` 的 A 记录指向服务器 `124.220.175.85`。如果配置了 AAAA 记录，也要确保其指向该服务器可用的 IPv6 地址，否则删除这条不适用的记录。腾讯云安全组与服务器防火墙需允许 TCP 80 和 443，且这两个宿主机端口不能已被其他进程占用。

在服务器仓库根目录的 `nginx/ssl/` 放置：

```text
nginx/ssl/llmops.qiuyouyou.cn_bundle.crt
nginx/ssl/llmops.qiuyouyou.cn.key
```

证书须覆盖 `llmops.qiuyouyou.cn`。`.crt` 为 PEM 格式的完整证书链，域名证书在前、中间证书在后；`.key` 为匹配的、可无交互加载的 PEM 私钥。下载包文件名不同时，可重命名为上述名称，或同步修改 `nginx/conf.d/default.conf` 的两个路径。证书链与权限要求见 [Nginx HTTPS 文档](https://nginx.org/en/docs/http/configuring_https_servers.html)。

```bash
mkdir -p nginx/ssl
# 上传证书与私钥后执行：
chmod 644 nginx/ssl/llmops.qiuyouyou.cn_bundle.crt
chmod 600 nginx/ssl/llmops.qiuyouyou.cn.key
docker compose -f compose.prod.yaml run --rm --no-deps llmops-nginx nginx -t
```

证书目录只读挂载到入口容器 `/etc/nginx/ssl`，无需重建镜像。没有证书文件时 Nginx 无法启动；配置检查通过后再启动入口。Git 和 Docker 构建已忽略证书目录中的文件，仅保留 `README.md` 说明。

若使用 GitHub 登录，将服务器 `llmops-api/.env` 中的 `GITHUB_REDIRECT_URI` 以及 GitHub OAuth App 的回调地址同步设置为 `https://llmops.qiuyouyou.cn/auth/authorize/github`；这是前端回调页面，不加 `/api` 前缀。环境变量变更后需要重新创建 API/Celery 容器。

## 5. 启动和检查应用

```bash
docker compose -f compose.prod.yaml up -d llmops-api llmops-celery llmops-web llmops-nginx
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml exec llmops-nginx nginx -t
docker compose -f compose.prod.yaml logs --tail=100 llmops-api llmops-celery llmops-nginx
curl -I http://llmops.qiuyouyou.cn/
curl --resolve llmops.qiuyouyou.cn:443:127.0.0.1 -fsS https://llmops.qiuyouyou.cn/
curl --resolve llmops.qiuyouyou.cn:443:127.0.0.1 -sS -i https://llmops.qiuyouyou.cn/api/apps
```

无 Token 的 `/api/apps` 应返回后端鉴权失败 JSON，用于检查代理、HTTP 与鉴权链路；不验证数据库 Schema、模型或业务成功。不要使用会调用模型的 `/api/ping`。Celery 日志应出现 `ready` 和注册的任务。

HTTP 检查应返回 308 和 HTTPS 地址；两个 HTTPS 检查通过本机端口验证证书及代理，不依赖公网 DNS。浏览器访问 `https://llmops.qiuyouyou.cn/`，不要使用 HTTPS IP 地址代替域名。前端 5173 和 API 5001 已不发布，不需要开放。登录、流式聊天、停止任务、文档索引需要随后进行真实业务验证，模型调用可能产生费用。

## 更新和数据保留

修改环境文件后重新创建 API/Celery，单独 `restart` 不会加载新配置：

```bash
docker compose -f compose.prod.yaml up -d --force-recreate llmops-api llmops-celery
```

代码更新后重建镜像；如果有数据库迁移，先备份并停止应用，执行一次迁移，再启动。升级本次入口代理配置时执行：

```bash
docker compose -f compose.prod.yaml build llmops-web
docker compose -f compose.prod.yaml up -d llmops-api llmops-celery llmops-web llmops-nginx
```

只修改入口 Nginx 配置文件时无需构建镜像，检查语法后重新加载：

```bash
docker compose -f compose.prod.yaml exec llmops-nginx nginx -t
docker compose -f compose.prod.yaml exec llmops-nginx nginx -s reload
```

从旧 HTTP 配置升级到本次 HTTPS 配置时，先上传证书并检查，再创建包含 443 端口与证书挂载的入口容器；单独 reload 不能新增 Docker 端口映射或挂载：

```bash
docker compose -f compose.prod.yaml run --rm --no-deps llmops-nginx nginx -t
docker compose -f compose.prod.yaml up -d --no-deps llmops-nginx
```

HTTPS 升级继续使用前端 `/api` 地址，无需再次构建前端。证书续期由服务器单独处理；更新 `nginx/ssl` 中的证书和私钥后执行 `nginx -t` 与 `nginx -s reload`，Nginx 会重新读取该目录中的文件。

`docker compose -f compose.prod.yaml down` 停止容器并保留 `volumes/` 中的绑定目录数据；不要删除这些目录。本地环境文件和已有数据目录属于服务器部署状态，更新代码时保留。
