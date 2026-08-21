# 本地开发手册

## 当前开发方式

项目最初在 PyCharm 中开发，后来迁移到 VS Code。当前后端日常启动方式以 `llmops-api/.vscode/launch.json` 为准：选择 `Development (Flask + Celery)` 后按 F5，同时启动 Flask API 和 Celery Worker。`uv` 仍然是 Python 依赖管理工具，并被 `tasks.json` 中的终端任务使用，但它不是唯一、也不是日常首选的 API 启动入口。

需要注意，`.vscode` 位于 `llmops-api/` 内，而不是仓库根目录：

- 推荐使用 VS Code 的 **File → Open Folder...**，直接打开 `llmops-api/`；
- 或在多根 Workspace 中把 `llmops-api/` 添加为独立 Workspace Folder；
- 如果只打开仓库根目录 `trace-llmops/`，VS Code 不会自动使用嵌套目录中的 `llmops-api/.vscode/launch.json` 和 `tasks.json`。

## 首次初始化

项目根目录负责 Docker Compose，`llmops-api/` 负责 Python 环境：

```bash
cp .env.example .env
cp llmops-api/.env.example llmops-api/.env
docker compose up -d
cd llmops-api
uv sync --locked
```

`.env.example` 只用于了解配置项。不要把真实密钥提交到仓库，也不要让 Codex 读取或输出 `.env`。项目通过 `.python-version` 选择 Python 3.11，并要求 uv 0.12.5 或更高版本。

随后在 VS Code 中执行 **Python: Select Interpreter**，选择：

```text
llmops-api/.venv/bin/python
```

在 macOS 上可以按 `⇧⌘P` 打开 Command Palette，搜索 `Python: Select Interpreter`。这一步很重要：F5 的 `launch.json` 通过 Python 扩展和 debugpy 启动 Flask，它使用的是 VS Code 当前选中的 Python Interpreter，而不是在配置中直接执行 `uv run`。

如果 VS Code 没有 `Python: Select Interpreter` 或 F5 无法识别 `debugpy` 配置，接受工作区推荐并安装或启用 Microsoft Python 与 Python Debugger 扩展。

## 使用 F5 启动完整开发进程

确保 VS Code 当前打开的是 `llmops-api/`，然后：

1. 先从仓库根目录执行 `docker compose up -d`，启动 PostgreSQL、Redis 和 Weaviate；
2. 确认状态栏选择的是 `.venv/bin/python`；
3. 打开 **Run and Debug** 面板；
4. 选择 `Development (Flask + Celery)`；
5. 按 F5。

这个 compound 配置会同时启动两个独立的 debugpy 进程：

- `Flask API`：以 `app.http.app:create_app` 为工厂启动 Flask；
- `Celery Worker`：以 `app.http.app:celery` 为 Celery 应用启动 Worker。

两个进程分别显示在集成终端中，都支持 Python 断点。compound 设置了 `stopAll`，停止任意一个调试会话时，VS Code 会停止本次 compound 启动的其余进程。以后增加常驻开发进程时，可以新增一个独立 configuration，再把它的名称加入 `compounds[].configurations`。

`Flask API` 使用 `--no-reload` 和 `--no-debugger`：代码仍运行在 Flask debug 模式，但关闭 Werkzeug 自带的 reloader 和 debugger，避免 reloader 创建第二个进程后造成重复初始化、断点命中混乱和停止不彻底。修改 Python 代码后按 `⇧F5`，再按 F5 重启 compound。

`Celery Worker` 使用 `--pool=solo`，让任务留在 debugpy 管理的当前进程中，断点和停止行为最可预测。这是本地调试配置，不是生产部署的并发方案。

需要只调试一个进程时，选择 `Flask API` 或 `Celery Worker` 后按 F5 即可。

F5 不会自动执行数据库迁移，也不会自动启动或停止 Docker Compose。迁移可能改变数据结构，Docker 基础设施通常跨多个调试会话复用，把它们绑定到每次 F5 会造成不必要的副作用。首次开发或基础设施未运行时，仍应先从仓库根目录执行 `docker compose up -d`。

## 使用 tasks.json 启动任务

正确文件名是 `tasks.json`（复数），位置是 `llmops-api/.vscode/tasks.json`。它当前定义了四个 Task：

| Task            | 作用                                                      | 日常启动是否需要                     |
| --------------- | --------------------------------------------------------- | ------------------------------------ |
| `celery worker` | 不进入调试器、单独启动 Celery Worker                      | 排查 Worker 启动或只观察任务日志时   |
| `db upgrade`    | 把当前开发数据库升级到最新迁移                            | 首次启动或拉取到新迁移后需要         |
| `db migrate`    | 根据 Model 变化生成新迁移                                 | 普通启动不需要                       |
| `db downgrade`  | 回退数据库迁移                                            | 普通启动禁止执行，可能改变或丢失数据 |

通常直接使用 `Development (Flask + Celery)`，不再需要手工另开终端。若只想运行 Worker 而不调试，可以运行 Celery Task：

1. 确认 Redis 等 Docker 服务已经启动；
2. 在 VS Code 中按 `⇧⌘P`；
3. 输入并选择 **Tasks: Run Task**；
4. 选择 `celery worker`；
5. VS Code 会打开一个专用集成终端并持续运行 Worker，日志直接显示在终端；
6. 需要停止时聚焦该终端，按 `Ctrl+C`，或点击终端的停止/垃圾桶按钮。

也可以通过菜单 **Terminal → Run Task...** 选择相同任务。Task 会在 `${workspaceFolder}` 下运行，所以这里同样要求 `llmops-api/` 是当前 Workspace Folder。

第一次初始化数据库时，可以用同样方式运行 `db upgrade`。该 Task 执行结束后终端会返回，不需要一直保持运行。

不要为了“试一下 tasks.json”而运行 `db migrate` 或 `db downgrade`：

- `db migrate` 会在 `internal/migrations/versions/` 生成迁移文件，应只在你主动修改 Model 后使用；
- `db migrate` 会提示输入迁移说明，并将其传给 `-m`；
- `db downgrade` 会提示输入目标 revision，默认是 `-1`；
- `db downgrade` 会回退数据库结构，只有明确理解目标迁移和数据影响时才能执行。

## 推荐的日常启动顺序

1. 从仓库根目录启动基础设施：`docker compose up -d`；
2. 在 VS Code 中直接打开 `llmops-api/`；
3. 选择 `Development (Flask + Celery)` 并按 F5；
4. 调试结束后按 `⇧F5`，Flask 和 Celery 会一起停止；
5. 基础设施不再使用时运行 `docker compose down`。

如果当前功能不涉及文档索引或其他异步任务，可以改选 `Flask API` 单独启动；Flask 本身不依赖 Worker 进程一直在线。

## 终端备用启动方式

不使用 VS Code 调试器时，也可以在终端启动 API：

```bash
cd llmops-api
uv run flask --app app.http.app:create_app run --debug
```

在另一个终端启动 Celery Worker：

```bash
cd llmops-api
uv run celery -A app.http.app:celery worker --loglevel=INFO --pool=solo
```

终端命令和 `.vscode` 配置是同一套应用入口的两种使用方式。文档中的 `uv run` 主要用于环境初始化、数据库命令、Celery Task 和无 IDE 场景。

停止基础设施但保留本地数据：

```bash
docker compose down
```

## 当前测试方式

```bash
cd llmops-api
uv run pytest
```

当前测试主要是 Handler 测试，收集测试时会创建 Flask 应用，并可能依赖 PostgreSQL、Redis、固定账号和已有数据。它们还不是完全离线的单元测试。执行前先确认：

- 数据库和 Redis 指向本地开发或专用测试环境；
- 不会读取生产密钥；
- 不会调用付费模型或公网服务；
- 测试产生的数据可安全清理。

仓库目前没有统一 Ruff、类型检查、CI 或隔离的集成测试环境。需要这些能力时，应作为独立学习任务逐项加入，不把它们写成已经存在的命令。

## Python 依赖维护

- `pyproject.toml` 只声明项目的直接运行依赖；测试工具等本地开发依赖放入 `[dependency-groups].dev`；
- `uv.lock` 锁定完整的直接和间接依赖树，必须和 `pyproject.toml` 一起提交；
- `uv sync` 默认包含 `dev` group；只安装运行依赖时使用 `uv sync --no-dev`；
- 不再手工维护 `requirements.txt`，也不要直接使用 `.venv/bin/pip install` 修改项目环境；
- 增删依赖优先使用 `uv add`、`uv add --dev` 和 `uv remove`，让 uv 同步更新声明和锁文件。

依赖变更后的最小检查：

```bash
uv lock --check
uv sync --locked --dry-run
uv pip check
```

精确 `uv sync` 会删除未声明的包。这是预期行为，可以及时发现只存在于某位开发者本机、却没有记录到项目中的旧 `pip install` 依赖。

当前文档解析代码支持 CSV、Markdown、PDF、PPT/PPTX 和 XLS/XLSX，相应 Unstructured extras 已写入项目依赖。Unstructured 还建议为完整的 PDF、图片和旧版 Office 支持安装 `libmagic`、Poppler、Tesseract 和 LibreOffice；它们是操作系统依赖，不会出现在 `uv.lock` 中。

本地嵌入模型同样不属于 Python 依赖，`internal/core/embeddings/` 也被 Git 忽略。首次使用文档索引前需要联网把模型及其自定义实现下载到应用使用的缓存目录：

```bash
uv run hf download Alibaba-NLP/gte-multilingual-base --cache-dir internal/core/embeddings
uv run hf download Alibaba-NLP/new-impl --cache-dir internal/core/embeddings
```

`EmbeddingsService` 当前设置了 `local_files_only=True`，所以运行期间不会自动补下载；部署和离线环境应在启动 Worker 前完成模型准备。

## 数据库迁移

创建迁移：

```bash
cd llmops-api
uv run flask --app app.http.app:create_app db migrate -m "迁移说明"
```

升级数据库：

```bash
uv run flask --app app.http.app:create_app db upgrade
```

学习和检查迁移时：

1. 先修改 SQLAlchemy Model；
2. 生成迁移后手动阅读 `upgrade()` 和 `downgrade()`；
3. 不要修改已有迁移历史；
4. downgrade 前再次核对数据库 URL，禁止在生产或重要数据上试验；
5. 后续建立专用测试数据库后，再机械验证空库升级和 upgrade—downgrade—upgrade。

## Celery 改动检查

- 新任务优先传递字符串 UUID、数字、字符串、列表和字典等可序列化数据；
- 在 Task 内重新查询 ORM 对象；
- 明确任务重复执行会发生什么；
- 修改任务注册后重启 Worker；
- 不要因为阅读一个任务就顺带重构全部 Celery 调用。

## SSE 改动检查

修改前先阅读 `docs/contracts/agent-stream-events.md`，再搜索所有生成位置：

```bash
rg -n 'event: |text/event-stream|QueueEvent' llmops-api
```

当前没有统一 SSE 编码器。若要新增或修改事件，应先解释兼容影响，再同时更新事件文档和对应测试。统一编码器、版本字段、sequence、重放等能力应分别作为明确任务实现。

## 常见问题

- F5 看不到 `Development (Flask + Celery)`：通常是因为只打开了仓库根目录，或者 Python/debugpy 扩展未启用。请直接打开 `llmops-api/` 后重试。
- **Tasks: Run Task** 中看不到 Celery/数据库任务：确认当前 Workspace Folder 是 `llmops-api/`，且 `.vscode/tasks.json` 未被 Workspace Trust 限制。
- compound 中只出现 Flask、没有 Celery：在 Run and Debug 下拉框中确认选择的是 `Development (Flask + Celery)`，而不是 `Flask API`。
- 修改代码后没有自动重载：调试配置有意关闭 Flask reloader；按 `⇧F5` 后再次按 F5，确保 Flask 和 Celery 使用同一版代码。
- API 启动失败：确认位于 `llmops-api/`，依赖已通过 `uv sync --locked` 安装，且两个 `.env` 文件的本地配置一致。
- Celery 收不到任务：确认 Redis 可用、Worker 使用正确的 `-A app.http.app:celery`，并在代码变化后重启 Worker。
- 文档索引失败：依次检查 PostgreSQL 中的文档状态、Celery 日志和 Weaviate 连通性。
- 单 Worker 可流式输出，多 Worker 异常：当前 Agent Queue 是进程内 Queue，不支持跨 API Worker 共享。
- Codex 改动范围过大：直接要求“只分析，不修改文件”或“先给方案，等我确认后再实现”。仓库的 `AGENTS.md` 已将其设为默认行为。
