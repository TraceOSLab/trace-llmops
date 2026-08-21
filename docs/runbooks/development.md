# 本地开发手册

## 当前开发方式

项目最初在 PyCharm 中开发，后来迁移到 VS Code。当前后端日常启动方式以 `llmops-api/.vscode/launch.json` 为准：在 VS Code 中按 F5 启动 Flask。`uv` 仍然是 Python 依赖管理工具，并被 `tasks.json` 中的终端任务使用，但它不是唯一、也不是日常首选的 API 启动入口。

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
```

`.env.example` 只用于了解配置项。不要把真实密钥提交到仓库，也不要让 Codex 读取或输出 `.env`。

随后在 VS Code 中执行 **Python: Select Interpreter**，选择：

```text
llmops-api/.venv/bin/python
```

在 macOS 上可以按 `⇧⌘P` 打开 Command Palette，搜索 `Python: Select Interpreter`。这一步很重要：F5 的 `launch.json` 通过 Python 扩展和 debugpy 启动 Flask，它使用的是 VS Code 当前选中的 Python Interpreter，而不是在配置中直接执行 `uv run`。

如果 VS Code 没有 `Python: Select Interpreter` 或 F5 无法识别 `debugpy` 配置，先安装或启用 Microsoft Python 扩展。

## 使用 F5 启动 Flask API

确保 VS Code 当前打开的是 `llmops-api/`，然后：

1. 先从仓库根目录执行 `docker compose up -d`，启动 PostgreSQL、Redis 和 Weaviate；
2. 确认状态栏选择的是 `.venv/bin/python`；
3. 打开 **Run and Debug** 面板；
4. 选择 `Flask (app/http/app.py)`；
5. 按 F5。

当前 `launch.json` 会执行 Flask Module，工作目录是 `${workspaceFolder}`，并设置：

- `FLASK_APP=app.http.app`
- `FLASK_DEBUG=1`
- `args=["run"]`

因此 F5 只负责启动 Flask API，不会自动启动 Docker、Celery Worker 或数据库迁移。

停止 API 时，在 VS Code 调试工具栏点击停止，或按 `⇧F5`。

## 使用 tasks.json 启动任务

正确文件名是 `tasks.json`（复数），位置是 `llmops-api/.vscode/tasks.json`。它当前定义了四个 Task：

| Task            | 作用                                                      | 日常启动是否需要                     |
| --------------- | --------------------------------------------------------- | ------------------------------------ |
| `celery worker` | 启动 Celery Worker，并把日志写入 `storage/log/celery.log` | 文档索引等异步任务需要               |
| `db upgrade`    | 把当前开发数据库升级到最新迁移                            | 首次启动或拉取到新迁移后需要         |
| `db migrate`    | 根据 Model 变化生成新迁移                                 | 普通启动不需要                       |
| `db downgrade`  | 回退数据库迁移                                            | 普通启动禁止执行，可能改变或丢失数据 |

第一次运行 Celery Task：

1. 确认 Redis 等 Docker 服务已经启动；
2. 在 VS Code 中按 `⇧⌘P`；
3. 输入并选择 **Tasks: Run Task**；
4. 选择 `celery worker`；
5. VS Code 会打开一个集成终端并持续运行 Worker；
6. 需要停止时聚焦该终端，按 `Ctrl+C`，或点击终端的停止/垃圾桶按钮。

也可以通过菜单 **Terminal → Run Task...** 选择相同任务。Task 会在 `${workspaceFolder}` 下运行，所以这里同样要求 `llmops-api/` 是当前 Workspace Folder。

第一次初始化数据库时，可以用同样方式运行 `db upgrade`。该 Task 执行结束后终端会返回，不需要一直保持运行。

不要为了“试一下 tasks.json”而运行 `db migrate` 或 `db downgrade`：

- `db migrate` 会在 `internal/migrations/versions/` 生成迁移文件，应只在你主动修改 Model 后使用；
- 当前 Task 没有填写迁移说明，真正创建迁移时更推荐在终端执行带 `-m` 的命令；
- `db downgrade` 会回退数据库结构，只有明确理解目标迁移和数据影响时才能执行。

## 推荐的日常启动顺序

1. 从仓库根目录启动基础设施：`docker compose up -d`；
2. 在 VS Code 中直接打开 `llmops-api/`；
3. 通过 **Tasks: Run Task → celery worker** 启动 Worker；
4. 选择 `Flask (app/http/app.py)` 并按 F5 启动 API；
5. 调试结束后停止 F5 和 Celery Terminal；基础设施不再使用时运行 `docker compose down`。

如果当前功能不涉及文档索引或其他异步任务，可以不启动 Celery Worker；F5 启动 Flask 本身不依赖 Worker 进程一直在线。

## 终端备用启动方式

不使用 VS Code 调试器时，也可以在终端启动 API：

```bash
cd llmops-api
uv run flask --app app.http.app:create_app run --debug
```

在另一个终端启动 Celery Worker：

```bash
cd llmops-api
uv run celery -A app.http.app:celery worker --loglevel=INFO
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

- F5 看不到 `Flask (app/http/app.py)`：通常是因为只打开了仓库根目录，或者 Python 扩展未启用。请直接打开 `llmops-api/` 后重试。
- **Tasks: Run Task** 中看不到 Celery/数据库任务：确认当前 Workspace Folder 是 `llmops-api/`，且 `.vscode/tasks.json` 未被 Workspace Trust 限制。
- `celery worker` 终端输出较少：当前 Task 使用了 `--logfile=storage/log/celery.log`，请查看该日志文件。
- API 启动失败：确认位于 `llmops-api/`，依赖已通过 `uv sync --locked` 安装，且两个 `.env` 文件的本地配置一致。
- Celery 收不到任务：确认 Redis 可用、Worker 使用正确的 `-A app.http.app:celery`，并在代码变化后重启 Worker。
- 文档索引失败：依次检查 PostgreSQL 中的文档状态、Celery 日志和 Weaviate 连通性。
- 单 Worker 可流式输出，多 Worker 异常：当前 Agent Queue 是进程内 Queue，不支持跨 API Worker 共享。
- Codex 改动范围过大：直接要求“只分析，不修改文件”或“先给方案，等我确认后再实现”。仓库的 `AGENTS.md` 已将其设为默认行为。
