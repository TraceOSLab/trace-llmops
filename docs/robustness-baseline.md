# 后端稳健性阶段 0：基线证据

日期：2026-09-22。业务代码基线：`b46f4a5`，开始时工作区干净。范围及问题跟踪见[稳健性计划](robustness-plan.md)。本文件记录实际结果，不将现有测试通过解释为功能已全面加固。

## 执行结果

| 检查 | 结果 | 证据与限制 |
| --- | --- | --- |
| 现有离线测试 | 88 passed，5 skipped，8 warnings | 5 个真实 Provider 冒烟测试显式关闭；其余测试使用本地目录、Fake/MockTransport 等。 |
| 空测试库升级 | 13 个迁移成功 | 原有迁移完整执行；随后通过 psql 查询 alembic_version，结果为 `b739fd026a81`。没有 downgrade。 |
| 现有 HTTP 集成测试 | 21 passed，1 teardown error | `require_all_routes_to_be_exercised` 中 `assert len(expected) == 85` 失败，实际为 90。最初运行 87 warnings；加入路由采集后仍有相同错误。 |
| 动态路由核对 | 90 个注册入口，85 个已访问 | 下表逐项对应实际测试；5 个遗漏为辅助 Agent 与统计分析。 |
| 外部服务真实联调 | 尚未执行 | 仅 PostgreSQL 为真实服务；未运行真实 Celery Worker、Redis、Weaviate、COS、OAuth 或付费模型验证。 |
| 前端 | 已排除 | 用户明确现阶段不处理前端；没有构建、类型检查或 UI 验证。 |

HTTP 的 teardown error 附着在最后一个模型目录测试上，但错误属于整套测试的覆盖断言，不是该模型接口自身断言失败。当前整套 HTTP 测试退出码为 1，不能标记为全绿。

缺失入口：

- `POST /assistant-agent/chat`
- `POST /assistant-agent/chat/<uuid:task_id>/stop`
- `GET /assistant-agent/messages`
- `POST /assistant-agent/delete-conversation`
- `GET /analysis/<uuid:app_id>`

## 隔离方式与复现

新增 [robustness_baseline.py](../scripts/robustness_baseline.py) 仅用于测试进程：清空继承的业务环境变量；禁用 Flask/python-dotenv 配置文件加载；关闭付费模型冒烟与自动 pytest 插件；阻止 Python socket 建连/DNS/发送；额外约束 psycopg2 只能连接固定本地测试库。unit 模式连该测试库也禁止访问。它不是原生代码或不可信代码的通用安全沙箱；后续新增原生网络客户端需要重新核查。

现有 `scripts/test.sh` 未被改动。本次使用更严格的入口，不直接运行会自动加载本地配置的旧入口。本机模型缓存和 FAISS 资产在工厂初始化时实际被加载；未下载模型，未调用真实 Embedding 推理，但干净机器缺少这些资产时结果可能不同。

复现时在仓库根目录启动已有测试服务：

```sh
docker compose -p trace-llmops-test -f docker-compose.test.yml up -d --wait --pull never
```

然后在 `llmops-api/` 分别执行：

```sh
uv run --offline --no-sync python ../scripts/robustness_baseline.py unit
uv run --offline --no-sync python ../scripts/robustness_baseline.py migrate
uv run --offline --no-sync python ../scripts/robustness_baseline.py integration
```

前提是已有依赖环境、本地模型/FAISS 资产和 PostgreSQL 镜像。禁止为了复现而连接开发数据库或开启真实模型测试。`--no-sync --offline` 不安装新依赖；当前 `.python-version` 的 `w3.11` 值被 uv 忽略，已登记为待修问题。

每次 runner 在系统临时目录的 `trace-robustness-baseline/` 生成 `unit.xml`、`integration.xml`；integration 另生成 `routes.json`，含每个 URL、方法、endpoint 和访问它的测试标识。报告随重跑覆盖，本文件保存本次结论与清单。最初控制台日志留在 `/private/tmp/trace-baseline-unit.log`、`/private/tmp/trace-baseline-migrate.log`、`/private/tmp/trace-baseline-integration.log`，不作为长期版本化证据。

测试完成后仅清理测试项目：

```sh
docker compose -p trace-llmops-test -f docker-compose.test.yml down
```

测试数据库使用 tmpfs；删除测试容器后数据消失。开发用 PostgreSQL/Redis/Weaviate 容器不在该 Compose 项目中。

## 后台任务与运行时清单

| 入口 | 调用链与现有状态 | 当前验证/后续阶段 |
| --- | --- | --- |
| `document_task.build_documents` | DocumentService → Celery → IndexingService.build_documents → 解析/切分/关键词/向量 | HTTP 替换 delay，真实 Worker 和重复投递未测；阶段 4。 |
| `document_task.update_document_enabled` | DocumentService → Celery → IndexingService.update_document_enabled | HTTP 替换 delay，启停竞争未测；阶段 4。 |
| `document_task.delete_document` | DocumentService → Celery → IndexingService.delete_document | HTTP 替换 delay，跨存储清理未测；阶段 4。 |
| `app_task.auto_create_app` | AssistantAgentService 的 create_app 工具 → Celery → AppService.auto_create_app | 无专门任务回归；阶段 5，外部生成依赖需 Fake。 |
| `demo_task.demo_task` | 日志 → sleep → 返回演示结果 | 未运行，不作为核心业务稳定性证据。 |
| Agent 核心 | FunctionCallAgent/LangGraph → AgentQueueManager → Service SSE → ConversationService | 真实后台线程配 Fake 模型/Redis 的终止与用量测试已通过；断连和实际持久化仍需阶段 5。 |
| 工作流 START、END | 参数进入图、结果输出 | HTTP 使用简单图及 Fake runtime，不代表真实全图已执行；阶段 6。 |
| 工作流 LLM | 模型配置 → Provider → 结果 | 有 LLMNode 单元测试；多节点集成未测。 |
| 工作流 TEMPLATE_TRANSFORM | 模板变量 → 文本 | 无专门节点测试；阶段 6。 |
| 工作流 DATASET_RETRIEVAL | 账号上下文 → 检索 | 无专门节点测试；阶段 4/6。 |
| 工作流 HTTP_REQUEST | 输入映射 → HTTP → 状态码/文本 | 无专门节点测试，缺 timeout；阶段 3/6。 |
| 工作流 CODE | AST 检查 → 进程内 exec → 字典输出 | 无专门节点测试，仅可信代码；阶段 6。 |
| 工作流 TOOL | 工具选择与参数 → 调用 | 无专门节点测试；阶段 3/6。 |
| 检索运行时 | SemanticRetriever / FullTextRetriever / RetrievalService；Embedding 缓存、Weaviate、本地 FAISS | hit HTTP 替换检索；真实相关性、过滤与一致性未验证。 |

内置工具目录包含 Google、DuckDuckGo、Wikipedia、Gaode、DALL·E、Time；供应商模型目录测试验证可见 OpenAI、DeepSeek、Moonshot、Doubao、Zhipu、Ollama 及部分隐藏兼容目录。以上是目录/实现存在的证据，不是外部 API 可用性证明。

## 离线测试范围

现有 11 个测试文件位于 `llmops-api/test/internal/`：

- Agent：`test_stream_termination.py`、`test_usage.py`。
- 模型：`test_language_model_manager.py`、`test_usage.py`、`test_usage_migration.py`、`test_language_model_smoke.py`（5 项跳过）。
- 工作流：`test_llm_node.py`。
- Service：`test_agent_usage_responses.py`、`test_agent_usage_persistence.py`、`test_conversation_service.py`、`test_language_model_service.py`。

参数化后共 93 项。单元测试中的保存参数检查不能替代实际 DB 持久化验收；HTTP 外部边界测试中有 Service 整体替换，也不能证明其内部逻辑正确。

## 逐路由清单

由本次隔离 HTTP 运行的 Flask url_map 与 request_started 记录生成；HEAD/OPTIONS 为隐式方法，不另计。访问记录不代表 Service 真实执行，更不代表异常路径完整覆盖。Handler 链中的 Service 调用来自静态 AST，间接调用仍需专项审查。

| 方法与 URL | Handler → 直接 Service 调用 | 实际访问测试 |
| --- | --- | --- |
| `GET /ping` | [ping](../llmops-api/internal/handler/app_handler.py#L363) | T03 |
| `POST /apps/<uuid:app_id>/debug` | [debug](../llmops-api/internal/handler/app_handler.py#L223) | T03 |
| `GET /oauth/<string:provider_name>` | [provider](../llmops-api/internal/handler/oauth_handler.py#L25) → `oauth_service.get_oauth_by_provider_name` | T18 |
| `POST /oauth/authorize/<string:provider_name>` | [authorize](../llmops-api/internal/handler/oauth_handler.py#L31) → `oauth_service.oauth_login` | T18 |
| `POST /auth/password-login` | [password_login](../llmops-api/internal/handler/auth_handler.py#L25) → `account_service.password_login` | T04 |
| `POST /auth/logout` | [logout](../llmops-api/internal/handler/auth_handler.py#L36) | T04 |
| `GET /account` | [get_current_user](../llmops-api/internal/handler/account_handler.py#L32) | T04, T08 |
| `POST /account/name` | [update_name](../llmops-api/internal/handler/account_handler.py#L38) → `account_service.update_account` | T04 |
| `POST /account/password` | [update_password](../llmops-api/internal/handler/account_handler.py#L56) → `account_service.update_password` | T04 |
| `POST /account/avatar` | [update_avatar](../llmops-api/internal/handler/account_handler.py#L47) → `account_service.update_account` | T04 |
| `POST /apps` | [create_app](../llmops-api/internal/handler/app_handler.py#L69) → `app_service.create_app` | T01, T02, T03, T07, T08 |
| `POST /apps/<uuid:app_id>/delete` | [delete_app](../llmops-api/internal/handler/app_handler.py#L78) → `app_service.delete_app` | T07 |
| `POST /apps/<uuid:app_id>` | [update_app](../llmops-api/internal/handler/app_handler.py#L84) → `app_service.update_app` | T07 |
| `GET /apps/<uuid:app_id>` | [get_app](../llmops-api/internal/handler/app_handler.py#L93) → `app_service.get_app` | T07 |
| `GET /apps` | [get_apps_with_page](../llmops-api/internal/handler/app_handler.py#L100) → `app_service.get_apps_with_page` | T07 |
| `POST /apps/<uuid:app_id>/copy` | [copy_app](../llmops-api/internal/handler/app_handler.py#L110) → `app_service.copy_app` | T07 |
| `GET /apps/<uuid:app_id>/draft-app-config` | [get_draft_app_config](../llmops-api/internal/handler/app_handler.py#L116) → `app_service.get_draft_app_config` | T01 |
| `POST /apps/<uuid:app_id>/draft-app-config` | [update_draft_app_config](../llmops-api/internal/handler/app_handler.py#L122) → `app_service.update_draft_app_config` | T01, T02 |
| `POST /apps/<uuid:app_id>/publish` | [publish_draft_app_config](../llmops-api/internal/handler/app_handler.py#L129) → `app_service.publish_draft_app_config` | T01 |
| `POST /apps/<uuid:app_id>/cancel-publish` | [cancel_publish_app_config](../llmops-api/internal/handler/app_handler.py#L135) → `app_service.cancel_publish_app_config` | T01 |
| `POST /apps/<uuid:app_id>/fallback-history` | [fallback_history_to_draft](../llmops-api/internal/handler/app_handler.py#L140) → `app_service.fallback_history_to_draft` | T01 |
| `GET /apps/<uuid:app_id>/publish-histories` | [get_publish_histories_with_page](../llmops-api/internal/handler/app_handler.py#L151) → `app_service.get_publish_histories_with_page` | T01 |
| `GET /apps/<uuid:app_id>/summary` | [get_debug_conversation_summary](../llmops-api/internal/handler/app_handler.py#L162) → `app_service.get_debug_conversation_summary` | T02 |
| `POST /apps/<uuid:app_id>/summary` | [update_debug_conversation_summary](../llmops-api/internal/handler/app_handler.py#L168) → `app_service.update_debug_conversation_summary` | T02 |
| `POST /apps/<uuid:app_id>/conversations/delete-debug-conversation` | [delete_debug_conversation](../llmops-api/internal/handler/app_handler.py#L179) → `app_service.delete_debug_conversation` | T02 |
| `GET /apps/<uuid:app_id>/conversations/messages` | [get_debug_conversation_messages_with_page](../llmops-api/internal/handler/app_handler.py#L209) → `app_service.get_debug_conversation_messages_with_page` | T02 |
| `POST /apps/<uuid:app_id>/conversations` | [debug_chat](../llmops-api/internal/handler/app_handler.py#L354) → `app_service.debug_chat` | T03 |
| `POST /apps/<uuid:app_id>/conversations/tasks/<uuid:task_id>/stop` | [stop_debug_chat](../llmops-api/internal/handler/app_handler.py#L348) → `app_service.stop_debug_chat` | T03 |
| `GET /builtin-apps/categories` | [get_builtin_app_categories](../llmops-api/internal/handler/builtin_app_handler.py#L26) → `builtin_app_service.get_categories` | T14 |
| `GET /builtin-apps` | [get_builtin_apps](../llmops-api/internal/handler/builtin_app_handler.py#L33) → `builtin_app_service.get_builtin_apps` | T14 |
| `POST /builtin-apps/add-builtin-app-to-space` | [add_builtin_app_to_space](../llmops-api/internal/handler/builtin_app_handler.py#L40) → `builtin_app_service.add_builtin_app_to_space` | T14 |
| `GET /builtin-tools` | [get_builtin_tools](../llmops-api/internal/handler/builtin_tool_handler.py#L27) → `builtin_tool_service.get_builtin_tools` | T15 |
| `GET /builtin-tools/<string:provider_name>/tools/<string:tool_name>` | [get_provider_tool](../llmops-api/internal/handler/builtin_tool_handler.py#L33) → `builtin_tool_service.get_provider_tool` | T15 |
| `GET /builtin-tools/<string:provider_name>/icon` | [get_provider_icon](../llmops-api/internal/handler/builtin_tool_handler.py#L39) → `builtin_tool_service.get_provider_icon` | T15 |
| `GET /builtin-tools/categories` | [get_categories](../llmops-api/internal/handler/builtin_tool_handler.py#L45) → `builtin_tool_service.get_categories` | T15 |
| `POST /api-tools/validate-openapi-schema` | [validate_openapi_schema](../llmops-api/internal/handler/api_tool_handler.py#L82) → `api_tool_service.parse_openapi_schema` | T06 |
| `POST /api-tools` | [create_api_tool_provider](../llmops-api/internal/handler/api_tool_handler.py#L44) → `api_tool_service.create_api_tool_provider` | T06 |
| `POST /api-tools/<uuid:provider_id>/delete` | [delete_api_tool_provider](../llmops-api/internal/handler/api_tool_handler.py#L76) → `api_tool_service.delete_api_tool_provider` | T06 |
| `POST /api-tools/<uuid:provider_id>` | [update_api_tool_provider](../llmops-api/internal/handler/api_tool_handler.py#L53) → `api_tool_service.update_api_tool_provider` | T06 |
| `GET /api-tools` | [get_api_tool_providers_with_page](../llmops-api/internal/handler/api_tool_handler.py#L31) → `api_tool_service.get_api_tool_providers_with_page` | T06 |
| `GET /api-tools/<uuid:provider_id>` | [get_api_tool_provider](../llmops-api/internal/handler/api_tool_handler.py#L62) → `api_tool_service.get_api_tool_provider` | T06 |
| `GET /api-tools/<uuid:provider_id>/tools/<string:tool_name>` | [get_api_tool](../llmops-api/internal/handler/api_tool_handler.py#L69) → `api_tool_service.get_api_tool` | T06 |
| `POST /upload-files/file` | [upload_file](../llmops-api/internal/handler/upload_file_handler.py#L26) → `cos_service.upload_file` | T20 |
| `POST /upload-files/image` | [upload_image](../llmops-api/internal/handler/upload_file_handler.py#L38) → `cos_service.get_file_url`, `cos_service.upload_file` | T20 |
| `POST /datasets` | [create_dataset](../llmops-api/internal/handler/dataset_handler.py#L36) → `dataset_service.create_dataset` | T09, T16 |
| `POST /datasets/<uuid:dataset_id>/delete` | [delete_dataset](../llmops-api/internal/handler/dataset_handler.py#L79) → `dataset_service.delete_dataset` | T09 |
| `POST /datasets/<uuid:dataset_id>` | [update_dataset](../llmops-api/internal/handler/dataset_handler.py#L52) → `dataset_service.update_dataset` | T09 |
| `GET /datasets` | [get_datasets_with_page](../llmops-api/internal/handler/dataset_handler.py#L61) → `dataset_service.get_datasets_with_page` | T09 |
| `GET /datasets/<uuid:dataset_id>` | [get_dataset](../llmops-api/internal/handler/dataset_handler.py#L45) → `dataset_service.get_dataset` | T09 |
| `GET /datasets/<uuid:dataset_id>/queries` | [get_dataset_queries](../llmops-api/internal/handler/dataset_handler.py#L72) → `dataset_service.get_dataset_queries` | T09 |
| `POST /datasets/<uuid:dataset_id>/documents` | [create_documents](../llmops-api/internal/handler/document_handler.py#L38) → `document_service.create_documents` | T11 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/delete` | [delete_document](../llmops-api/internal/handler/document_handler.py#L98) → `document_service.delete_document` | T11 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/name` | [update_document_name](../llmops-api/internal/handler/document_handler.py#L76) → `document_service.update_document` | T11 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/enabled` | [update_document_enabled](../llmops-api/internal/handler/document_handler.py#L87) → `document_service.update_document_enabled` | T11 |
| `GET /datasets/<uuid:dataset_id>/documents` | [get_documents_with_page](../llmops-api/internal/handler/document_handler.py#L53) → `document_service.get_documents_with_page` | T11 |
| `GET /datasets/<uuid:dataset_id>/documents/<uuid:document_id>` | [get_document](../llmops-api/internal/handler/document_handler.py#L67) → `document_service.get_document` | T11 |
| `GET /datasets/<uuid:dataset_id>/documents/batch/<string:batch>` | [get_documents_status](../llmops-api/internal/handler/document_handler.py#L104) → `document_service.get_documents_status` | T11 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments` | [create_segment](../llmops-api/internal/handler/segment_handler.py#L48) → `segment_service.create_segment` | T12 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>/delete` | [delete_segment](../llmops-api/internal/handler/segment_handler.py#L76) → `segment_service.delete_segment` | T12 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>` | [update_segment](../llmops-api/internal/handler/segment_handler.py#L58) → `segment_service.update_segment` | T12 |
| `POST /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>/enabled` | [update_segment_enabled](../llmops-api/internal/handler/segment_handler.py#L67) → `segment_service.update_segment_enabled` | T12 |
| `GET /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments` | [get_segments_with_page](../llmops-api/internal/handler/segment_handler.py#L30) → `segment_service.get_segments_with_page` | T12 |
| `GET /datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>` | [get_segment](../llmops-api/internal/handler/segment_handler.py#L41) → `segment_service.get_segment` | T12 |
| `POST /datasets/<uuid:dataset_id>/hit` | [hit](../llmops-api/internal/handler/dataset_handler.py#L85) → `dataset_service.hit` | T16 |
| `POST /ai/optimize-prompt` | [optimize_prompt](../llmops-api/internal/handler/ai_handler.py#L26) → `ai_service.optimize_prompt` | T13 |
| `POST /ai/suggested-questions` | [generate_suggested_questions](../llmops-api/internal/handler/ai_handler.py#L35) → `ai_service.generate_suggested_questions_from_message_id` | T13 |
| `POST /openapi/api-keys` | [create_api_key](../llmops-api/internal/handler/api_key_handler.py#L30) → `api_key_service.create_api_key` | T05 |
| `POST /openapi/api-keys/<uuid:api_key_id>/delete` | [delete_api_key](../llmops-api/internal/handler/api_key_handler.py#L39) → `api_key_service.delete_api_key` | T05 |
| `POST /openapi/api-keys/<uuid:api_key_id>` | [update_api_key](../llmops-api/internal/handler/api_key_handler.py#L45) → `api_key_service.update_api_key` | T05 |
| `POST /openapi/api-keys/<uuid:api_key_id>/is-active` | [update_api_key_is_active](../llmops-api/internal/handler/api_key_handler.py#L54) → `api_key_service.update_api_key_is_active` | T05 |
| `GET /openapi/api-keys` | [get_api_keys_with_page](../llmops-api/internal/handler/api_key_handler.py#L63) → `api_key_service.get_api_keys_with_page` | T05 |
| `POST /workflows` | [create_workflow](../llmops-api/internal/handler/workflow_handler.py#L30) → `workflow_service.create_workflow` | T10, T21 |
| `POST /workflows/<uuid:workflow_id>/delete` | [delete_workflow](../llmops-api/internal/handler/workflow_handler.py#L39) → `workflow_service.delete_workflow` | T10 |
| `POST /workflows/<uuid:workflow_id>` | [update_workflow](../llmops-api/internal/handler/workflow_handler.py#L45) → `workflow_service.update_workflow` | T10 |
| `GET /workflows/<uuid:workflow_id>` | [get_workflow](../llmops-api/internal/handler/workflow_handler.py#L54) → `workflow_service.get_workflow` | T10 |
| `GET /workflows` | [get_workflows_with_page](../llmops-api/internal/handler/workflow_handler.py#L61) → `workflow_service.get_workflows_with_page` | T10 |
| `POST /workflows/<uuid:workflow_id>/draft-graph` | [update_draft_graph](../llmops-api/internal/handler/workflow_handler.py#L71) → `workflow_service.update_draft_graph` | T10, T21 |
| `GET /workflows/<uuid:workflow_id>/draft-graph` | [get_draft_graph](../llmops-api/internal/handler/workflow_handler.py#L79) → `workflow_service.get_draft_graph` | T10 |
| `POST /workflows/<uuid:workflow_id>/debug` | [debug_workflow](../llmops-api/internal/handler/workflow_handler.py#L85) → `workflow_service.debug_workflow` | T21 |
| `POST /workflows/<uuid:workflow_id>/publish` | [publish_workflow](../llmops-api/internal/handler/workflow_handler.py#L93) → `workflow_service.publish_workflow` | T10 |
| `POST /workflows/<uuid:workflow_id>/cancel-publish` | [cancel_publish_workflow](../llmops-api/internal/handler/workflow_handler.py#L99) → `workflow_service.cancel_publish_workflow` | T10 |
| `GET /language-models` | [get_language_models](../llmops-api/internal/handler/language_model_handler.py#L20) → `language_model_service.get_language_models` | T17 |
| `GET /language-models/<string:provider_name>/<string:model_name>` | [get_language_model](../llmops-api/internal/handler/language_model_handler.py#L25) → `language_model_service.get_language_model` | T17 |
| `GET /language-models/<string:provider_name>/icon` | [get_language_model_icon](../llmops-api/internal/handler/language_model_handler.py#L31) → `language_model_service.get_language_model_icon` | T17 |
| `POST /assistant-agent/chat` | [assistant_agent_chat](../llmops-api/internal/handler/assistant_agent_handler.py#L30) → `assistant_agent_service.assistant_agent_chat` | **未覆盖** |
| `POST /assistant-agent/chat/<uuid:task_id>/stop` | [stop_assistant_agent_chat](../llmops-api/internal/handler/assistant_agent_handler.py#L43) → `assistant_agent_service.stop_assistant_agent_chat` | **未覆盖** |
| `GET /assistant-agent/messages` | [get_assistant_agent_messages_with_page](../llmops-api/internal/handler/assistant_agent_handler.py#L49) → `assistant_agent_service.get_assistant_agent_messages_with_page` | **未覆盖** |
| `POST /assistant-agent/delete-conversation` | [delete_assistant_agent_conversation](../llmops-api/internal/handler/assistant_agent_handler.py#L66) → `assistant_agent_service.delete_assistant_agent_conversation` | **未覆盖** |
| `GET /analysis/<uuid:app_id>` | [get_app_analysis](../llmops-api/internal/handler/analysis_handler.py#L17) → `analysis_service.get_app_analysis` | **未覆盖** |
| `POST /openapi/chat` | [chat](../llmops-api/internal/handler/openapi_handler.py#L26) → `openapi_service.chat` | T19 |

## HTTP 测试索引

- **T01**：[test_app_config_publish_history_and_fallback_routes](../llmops-api/test/integration/handler/test_app_runtime_http_routes.py)
- **T02**：[test_app_debug_conversation_routes](../llmops-api/test/integration/handler/test_app_runtime_http_routes.py)
- **T03**：[test_app_debug_stream_stop_and_ping_routes](../llmops-api/test/integration/handler/test_app_runtime_http_routes.py)
- **T04**：[test_account_and_auth_routes_use_real_database](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T05**：[test_api_key_crud_routes_persist_and_query](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T06**：[test_api_tool_crud_routes_persist_and_query](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T07**：[test_app_crud_routes_persist_and_query](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T08**：[test_authentication_and_validation_failures](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T09**：[test_dataset_crud_routes_persist_and_query](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T10**：[test_workflow_crud_and_graph_routes_persist_and_query](../llmops-api/test/integration/handler/test_database_http_routes.py)
- **T11**：[test_document_routes_persist_and_query](../llmops-api/test/integration/handler/test_document_segment_http_routes.py)
- **T12**：[test_segment_routes_persist_and_query](../llmops-api/test/integration/handler/test_document_segment_http_routes.py)
- **T13**：[test_ai_routes_never_call_models](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T14**：[test_builtin_app_routes](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T15**：[test_builtin_tool_routes](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T16**：[test_dataset_hit_uses_real_dataset_and_fake_retrieval](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T17**：[test_language_model_routes_use_local_service_boundary](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T18**：[test_oauth_routes_use_real_http_and_schema](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T19**：[test_openapi_chat_uses_api_key_and_fake_model](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T20**：[test_upload_routes_use_multipart_without_cos](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)
- **T21**：[test_workflow_debug_stream_uses_fake_runtime](../llmops-api/test/integration/handler/test_external_boundary_http_routes.py)

