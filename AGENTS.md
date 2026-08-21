# Trace LLMOps 仓库协作指南

## 项目地图

- `llmops-api/` 是当前主要开发目录，后端技术栈包括 Flask、SQLAlchemy、Celery、Redis、PostgreSQL、Weaviate、Pydantic v2、LangChain 和 LangGraph。
- `llmops-web/` 目前只是 Vue/Vite 初始脚手架。在前端正式开发前，不要预设前端规范。
- `docker-compose.yml` 只用于启动本地基础设施。
- 修改跨层边界前，先阅读 `docs/architecture.md`。

## 标准命令

- 后端日常开发以 `llmops-api/.vscode/launch.json` 的 VS Code F5 调试配置为首选启动方式；`uv` 负责依赖和终端任务，不要把 `uv run` 描述成唯一启动入口。
- Python 依赖使用 `uv`，前端依赖使用 `pnpm`。
- 使用 `docker compose up -d` 启动 PostgreSQL、Redis 和 Weaviate。
- VS Code 应直接打开 `llmops-api/`，或将它作为独立 Workspace Folder；后端的 F5 与 Task 操作见 `docs/runbooks/development.md`。
- 修改后先运行与改动最相关的最小检查。当前测试依赖真实环境，运行前先确认不会访问付费模型或生产资源。

## 协作约定

- 这是学习项目：默认由开发者手写代码，Codex 负责理解代码、解释、审查、排错和提供小段建议。只有用户明确说“实现”“修改”或“帮我写”时才编辑代码。
- 用户只是提问、讨论方案或请 Codex 检查时，保持只读；回答应指出相关文件、调用链、设计取舍和可能的失败方式。
- 优先做符合现有架构、范围小且便于学习的改动。不要仅因为整体重写更整洁就替换子系统或大批量生成业务功能。
- 不读取、不输出、不提交 `.env`；只可通过 `.env.example` 了解配置项名称。
- 保留用户无关的未提交改动。编辑前和交付前都要检查 `git status`。
- 不修改已有迁移历史；修复 Schema 时新增迁移。
- 默认测试禁止调用付费模型 API 或公网服务。
- `AGENTS.md` 保持简短。架构知识和操作步骤放入 `docs/`；重复流程真正稳定后再建立 Skill。

## 跨模块变更要求

- 数据库变更应新增迁移，不得修改已有迁移历史；执行 downgrade 前必须确认目标是开发或测试数据库。
- Celery 任务参数应可序列化，并考虑重试和重复投递。
- SSE 变更前先阅读 `docs/contracts/agent-stream-events.md`，同步更新文档和相关测试。
- 修改运行架构、接口契约或基础设施前，先解释影响并征得用户明确同意。
