# 已有后端功能稳健性加固计划

## 范围与推进规则

基线日期：2026-09-22；业务代码基线：`b46f4a5`。本轮仅覆盖已有后端功能，按用户最新要求排除前端。使用场景为本人或可信开发者，保留本机和内网调用能力；代码节点只执行可信代码，不将 AST 校验视为安全沙箱。

每阶段验收后再继续。每批先复现，再做最小修复和回归；每次交付问题、改动、测试结果及未验证边界。默认不修改路由、错误码、响应结构和 SSE 契约；需要改变接口、运行架构或基础设施时另行确认。数据库变化只新增迁移，不读取 `.env`，不使用生产数据或付费模型，不自动提交或推送。

计划状态：**全部七个阶段已完成**。明确列为“受限”或“用户暂缓”的事项不视为已解决。

状态含义：**待检查**＝未完成专项审查；**已确认问题**＝有静态代码或运行证据，需注明证据类型；**已修复**＝已实施但尚未完成验证；**已验证**＝限定场景有验证证据；**受限**＝尚有环境或架构边界。阶段 0 完成不代表功能加固完成。

## 阶段进度

| 阶段 | 状态 | 内容与验收标准 |
| --- | --- | --- |
| 0 基线 | 已验收 | 90 个接口、5 个 Celery 任务和 8 类工作流节点已列清单；离线测试、独立库迁移、HTTP 测试已执行；历史基线保留覆盖失败，详见[基线证据](robustness-baseline.md)。 |
| 1 认证与公共基础 | 按用户要求收尾，保留明确限制 | 第一批已验收；补 OAuth 并发登录事务锁和 6 项真实数据库回归。JWT 撤销和 OAuth state 不继续扩展，见 B18/B19。 |
| 2 应用与配置生命周期 | 本批已验收 | 应用 CRUD、复制、草稿、发布、取消发布、历史回退、内置应用及新增 WebApp 凭证；76 项集成通过，本批证据见下文。用户要求暂不改造逻辑删除；会话与运行中任务清理留到阶段 5。 |
| 3 模型、工具与外部调用 | 已完成，外部验证受限 | 模型目录/工厂/结构化输出、全部 6 类内置工具、自定义工具、OAuth、上传及启动依赖均已检查。212 项离线、84 项数据库集成通过；可选 SDK 和真实外部服务限制见阶段交付，不视为已验证。 |
| 4 知识库与索引 | 已完成，真实竞争联调受限 | 知识库、文档、片段、启停、删除、关键词、向量和混合检索；已验证任务派发失败、重复投递、删除失败与派生数据残留边界。真实 Weaviate/Celery 竞争联调受限，见阶段交付。 |
| 5 对话与 Agent | 已完成，真实断网/跨进程取消受限 | 调试/公开 API/辅助 Agent、消息历史、摘要、停止和用量；断连持久化、单次终止、错误/停止/超时用量和旧调试流异常已验证。真实客户端断网及跨进程取消受限，见阶段交付。 |
| 6 工作流与 AI 辅助 | 已完成，代码与外部节点受限 | 草稿图、发布、调试、节点、提示词优化与建议问题已审查；串行图、变量引用、运行时工具归属和调试失败收尾已验证。代码节点和真实外部节点受限，见阶段交付。 |
| 7 统计与总体验收 | 已完成，缓存真实服务验证受限 | 指标、趋势、费用和缓存已审查；B08 已修复，空数据、日期边界、Decimal、缓存读写故障和统计 HTTP 路径已回归；全量离线及独立 PostgreSQL 回归通过。 |

阶段内优先级：越权或数据损坏 → 请求挂起或功能不可用 → 错误结果 → 可维护性与性能。已有实现满足要求时只补验证，不批量重写。

## 功能—调用链—测试—缺口

下表路径均相对 `llmops-api/`。每个具体 URL、Handler、直接 Service 调用和实际访问它的测试见[逐路由清单](robustness-baseline.md#逐路由清单)。表中的“覆盖”仅指当前测试检查了部分行为。

| 功能 | 主要调用链 | 现有测试 | 后续缺口 |
| --- | --- | --- | --- |
| 登录、退出、OAuth、账号、API Key | Router → Middleware/Handlers → Account/OAuth/JWT/ApiKeyService → PostgreSQL/外部 OAuth | HTTP database/external 两组测试 | 权限矩阵、无效凭证、OAuth 失败、敏感错误 |
| 应用、配置、复制、发布与回退 | AppHandler → AppService/AppConfigService → App/AppConfigVersion/关联表 | HTTP database/app_runtime | 并发、历史快照隔离、引用删除与权限 |
| 内置应用 | BuiltinAppHandler → BuiltinAppService → 配置目录/AppService | HTTP external，Service 被替换 | 实际模板解析、引用校验、复制与隔离 |
| 文件与图片上传 | UploadFileHandler → CosService/UploadFileService → COS/UploadFile | HTTP multipart，COS 被替换 | 类型/大小限制、持久化失败、清理 |
| 知识库、文档与片段 | Dataset/Document/SegmentHandler → 对应 Service → DB/关键词/向量/Celery | HTTP database/document_segment；外部边界为 Fake | 重试、竞争、索引状态与跨存储一致性 |
| 检索、Embedding 与本地 FAISS | RetrievalService → Semantic/FullTextRetriever；EmbeddingsService/VectorDatabaseService/FaissService | HTTP hit 的检索被替换；启动实际加载了本地模型 | 实际召回过滤、租户隔离、模型/索引兼容与资源释放 |
| 内置与自定义工具 | BuiltinTool/ApiToolHandler → Service → ProviderManager → 工具 | HTTP CRUD 与外部 Fake | 运行时参数、超时、非成功响应、可选字段 |
| 模型管理与结构化输出 | LanguageModelHandler → Service → LanguageModelManager → Provider | 本地目录/工厂/结构化输出单元测试；HTTP Service 被替换 | 失败与重试边界；真实供应商行为仍未验证 |
| 调试与公开应用对话 | App/OpenApiHandler → Service → FunctionCallAgent/Queue → ConversationService → Message/Thought | HTTP Fake + 真实 LangGraph/Fake 模型单元测试 + 保存参数/用量测试 | 断流持久化、重复保存、并发会话、真实任务取消 |
| 辅助 Agent/自动创建应用 | AssistantAgentHandler → AssistantAgentService → Agent/FaissService；auto_create_app → AppService | 无 HTTP 路由覆盖；共享 Agent 核心有测试 | 4 个入口、账号隔离、历史清理及创建任务 |
| 工作流 | WorkflowHandler → WorkflowService → Workflow → 8 类节点 | HTTP CRUD/图保存/发布；debug 替换 runtime；LLMNode 单元测试 | 实际全图执行、节点失败、分支汇合与变量类型 |
| AI 辅助、摘要与标题 | AIHandler/ConversationService → LanguageModelManager | HTTP Fake；标题/建议问题解析与 fallback 单元测试 | 真实优化流的异常/断连与摘要并发 |
| 用量与费用 | Provider usage → Agent 汇总 → SSE/非流式/历史/DB usage | token、Decimal、价格快照、迁移、序列化和保存测试 | 异常终止后真实 DB 状态、统计口径衔接 |
| 统计分析 | AnalysisHander → AnalysisService → AppService/Message/Redis | 无专门测试，无 HTTP 访问记录 | 认证、时间边界、未知费用、缓存读写故障 |
| 演示入口 | `/ping`、`/apps/<app_id>/debug`、demo_task | HTTP 演示线程/图为 Fake；demo_task 无测试 | 与正式运行入口区分，检查副作用与失败处理 |

HTTP 测试文件缩写对应 `test/integration/handler/test_*_http_routes.py`；具体测试标识在基线文档中逐项列出。离线文件目录为 `test/internal/`。

## 已确认问题与待验证风险

| ID | 状态/证据 | 问题与后续动作 |
| --- | --- | --- |
| B01 | 已修复并验证 | 改为 endpoint+method 集合差异检查；新增辅助 Agent 与统计用例。90/90 均在匿名拒绝矩阵以外有访问记录；并非只将 85 改成 90。 |
| B02 | 已修复并验证 | 统计及历史回退入口增加显式登录保护；全部非公开入口经过匿名拒绝矩阵；统计用真实业务计算及两个账号验证权限，未将原问题表述为已证实泄露。 |
| B03 | 已修复并验证 | 非调试未处理异常返回通用消息，保留 HTTP 200 与 fail 结构；服务端只记录异常类型，避免原始异常中含 SQL/凭证。业务异常及调试模式保持原有行为。 |
| B04 | 已修复并验证，Fake HTTP | HTTP 节点和自定义工具补连接 5 秒、读取 30 秒超时及响应关闭；验证超时/连接错误不重试，保留文本和状态码输出。此超时不是整个工作流的墙钟时限。 |
| B05 | 已修复并验证 | 动态工具的非必填字段增加默认 None；省略可选参数成功，缺少必填参数仍触发 ValidationError。 |
| B06 | 待检查：调用链风险 | App/OpenApi/AssistantAgentService 在流式循环结束后启动保存线程；阶段 5 验证 Generator 断连/关闭时是否丢失保存，并验证线程失败。 |
| B07 | 受限：静态 | CodeNode 在 API 进程内 exec；本轮仅用于可信代码，不能保证安全隔离或任意代码强制超时。 |
| B08 | 已修复并验证 | AnalysisService 缓存读取或 JSON 解析失败会重算；缓存 setex 写入异常现只记录日志并返回已计算统计。构造的损坏缓存、写入故障、空数据及真实 HTTP 路径均有回归。 |
| B09 | 已修复并验证，首次检索仍依赖本地资产 | FAISS 改为带锁延迟加载；Fake 验证并发只加载一次、失败可重试；真实 Flask/迁移启动不再触发 Embedding 加载。模型缓存封装成功后才发布实例，路径改为相对源码。未证明没有任何依赖的干净机器可直接启动。 |
| B10 | 已修复，现有环境验证 | `.python-version` 修正为 `3.11`，uv 不再报告无效声明；未重新安装全部依赖，不将现有虚拟环境通过等同于新环境复现完成。 |
| B11 | 已修复并验证，限标准测试入口 | `scripts/test.sh` 统一调用隔离 runner；四组旧 HTTP 测试的依赖替换使用 monkeypatch 自动恢复。共享 app_context 导致 g 缓存跨请求复用登录用户的问题也已修正；仅测试 fixture 每次请求清理 `_login_user`，不修改生产认证缓存。直接运行任意 pytest 命令不自动获得 runner 的网络隔离。 |
| B12 | 已修复并验证 | JWT 要求 sub/iss/exp、限定 llmops 签发者并校验 UUID；失效签名、过期、缺失字段和不存在账号均按 unauthorized 拒绝。仅接受已有登录接口本来就签发的完整凭证结构。 |
| B13 | 已修复并验证 | Bearer 空值、纯空白、多段值不再抛解析异常；孤立或停用/已删除 API Key 不得认证。 |
| B14 | 已修复并验证 | auto_commit 对事务体/commit 异常 rollback 并重抛；真实 PostgreSQL 约束失败后未残留失败记录，同 Session 能继续成功写入。 |
| B15 | 已修复并验证 | 分页显式空值不再绕过校验；历史版本列表补 validate；辅助 Agent 消息列表读取 request.args；空校验错误集合可安全序列化。 |
| B16 | 已修复并验证，GitHub 请求为 Fake | 仅用 verified=true 的主邮箱关联账号，缺失身份不再构造虚假邮箱；显示名为空时用 login。未验证或缺失主邮箱的 OAuth 登录现在被拒绝，已有正常请求响应字段不变。 |
| B17 | 已修复并验证 | OAuth 账号创建、授权绑定、登录信息更新与本地 token 生成纳入一次事务；签名失败不留下新账号/绑定，已存在账号可保留，重复顺序登录只保留一个绑定并更新 token。 |
| B18 | 已修复并验证，限 OAuth 服务写入路径 | 以 OAuth 身份和邮箱的稳定哈希获取 PostgreSQL 事务 advisory lock，固定加锁次序并限制等待 5 秒。真实并发验证同身份、共享邮箱、邮箱变化、独立身份、失败回滚及锁超时。没有新增唯一约束，不合并已有重复数据，不保证绕过该服务的其他写入路径。 |
| B19 | 受限：用户要求暂缓 | logout 不撤销已签发 JWT，改密未引入令牌版本/撤销存储，OAuth 回调没有 state 校验。用户要求此处简单处理并进入下一阶段，因此不扩大实现范围；这些能力仍未实现。 |

当前费用趋势已经显式转 float，不把旧的 Decimal 序列化问题重复认定为现存错误；仍需阶段 7 做回归。已存在的 Agent 单次终止实现同样不重写，后续只针对新复现的问题修改。

## 阶段 0 交付与下一步

- 新增受控测试入口 `scripts/robustness_baseline.py`，不修改业务实现、迁移历史或既有测试断言。
- 结果：离线 88 passed / 5 skipped；独立库 13 个迁移成功，数据库 head 为 `b739fd026a81`；HTTP 21 passed / 1 teardown error，90 个入口访问了 85 个。
- 前端已按最新要求排除；收到调整前依赖安装已结束，未运行构建/测试，未改动前端源码或锁文件；生成的根目录缓存已移到临时目录。
- 测试库清理后不保留数据；后续需要时按基线文档重新建立。未对开发容器执行重启、迁移或删除。
- 阶段 0 已验收；以下记录阶段 1 第一批，阶段 2—7 尚未开始。

## 阶段 1 第一批交付（2026-09-22）

### 修复与验证

不改变现有 API 路由、响应字段、业务错误码、SSE、数据库 Schema 或部署架构。本批限制的是本来就无效的凭证、分页参数及不可信的 OAuth 身份数据；非调试错误文本改为脱敏文案。

- 最初新增回归：15 项失败，覆盖 JWT 缺失/非法声明、Bearer 解析、rollback、内部错误泄露、空校验错误、空分页参数。
- OAuth 身份回归先出现 4 项失败；真实数据库进一步复现两种登录失败留下绑定的情况（新账号/已有账号）。这些失败均已修复。
- 另一个“删除密钥仍通过认证”的回归失败定位到测试 app_context 的登录身份缓存，未认定为生产密钥撤销漏洞；修正 fixture 后该用例验证真实密钥查找。
- 最终离线：**118 passed / 5 skipped / 8 warnings**；HTTP：**49 passed / 247 warnings**。警告主要为既有 SQLAlchemy/Marshmallow/Pydantic 等弃用提示，未做无关批量迁移。
- 90/90 注册路由已访问，且去掉匿名矩阵的访问记录后仍为 90/90。覆盖检查按 endpoint+method 比较；覆盖不等于每个异常场景已验证。
- 两账号验证应用/知识库/工作流/API 工具/API Key 的列表隔离、读取、修改和删除；真实 DB 检查未授权操作后记录不变。嵌套文档/片段验证错误父级及其他账号访问。
- 新增统计成功响应由真实 AnalysisService 计算（Redis Fake）；辅助 Agent chat/stop 为 Service 边界 Fake，消息分页和清空会话关联走真实 DB。这不替代后续 Agent/统计专项阶段。
- `sh scripts/test.sh` 已从标准入口实际跑通，自动清理测试容器。全程未读取 `.env`、未调用真实模型或 GitHub/COS 服务、未修改前端；未提交或推送。

回归源码：

- [认证与公共基础离线回归](../llmops-api/test/internal/service/test_auth_foundation.py)
- [OAuth 身份离线回归](../llmops-api/test/internal/service/test_oauth_identity.py)
- [真实 HTTP、权限与数据库回归](../llmops-api/test/integration/handler/test_security_http_routes.py)

本次控制台证据：`/private/tmp/trace-stage1-unit-red.log`、`/private/tmp/trace-stage1-oauth-red.log`、`/private/tmp/trace-stage1-oauth-integration-red.log`、`/private/tmp/trace-stage1-unit.log`、`/private/tmp/trace-stage1-standard-entry.log`。最新 XML/routes.json 位于系统临时目录 `trace-robustness-baseline/`；重跑会覆盖，长期结论以上述计数和回归源码为准。

### 下一批与验收边界

第一批已验收；后续完成 B18 的轻量事务串行化修复。按用户最新要求，不继续扩展 B19，进入阶段 2。真实 OAuth 网络错误与超时留在阶段 3；知识库/Agent 并发仍按各自阶段推进。

计划与阶段 0 文档目前受仓库原有 `docs/` 忽略规则影响，是本地进度文件；本次未改动用户的忽略规则。后续若需要提交文档，应在提交前单独纳入版本管理。

最终完成要求：所有已有功能都有审查状态和证据；范围内缺陷修复且回归通过；关键链路完成隔离联调；不能解决的架构限制明确列出并由用户验收。

## 阶段 1 收尾与阶段 2 交付（2026-09-23）

本批基于当前 `6b3c165`，包含用户新增的 WebApp 基础功能；不涉及前端。当前注册接口由历史基线的 90 个增加到 93 个。保留历史基线记录，不将新代码误记为阶段 0 已验证内容。

### 认证收尾

- B18 回归最初 3 项失败；修复后 6 项并发测试通过，当时全部集成为 55 passed。覆盖同身份首次登录、不同身份共享邮箱、身份邮箱变化、不相关身份不互相阻塞、失败回滚和锁超时释放。
- 使用现有 PostgreSQL 的事务锁，没有新增迁移或基础设施。签名失败仍整体回滚，锁随事务结束释放。
- B19 按用户要求暂缓，不把 JWT 撤销或 OAuth state 记为已实现。
- 用量迁移测试不再把历史用量迁移写死为最新 head，改为检查只有一个活动 head 且用量迁移仍在迁移链中；原 DDL 精度断言保留。独立测试库已跑通用户新增的 `b1263027e476` 迁移，未修改迁移历史。

证据：[OAuth 并发测试](../llmops-api/test/integration/test_oauth_concurrency.py)，日志 `/private/tmp/trace-stage1b-red.log`、`/private/tmp/trace-stage1b-final.log`。

### 应用生命周期问题及修复

| ID | 复现条件 | 修复与验证 |
| --- | --- | --- |
| C01 | 回退接口传入其他应用的版本，或草稿版本 | 查询同时限定应用 ID 和 published 类型；同账号其他应用及跨账号均拒绝，目标草稿不变。 |
| C02 | 发布写历史失败，或取消发布删除关联失败 | 运行配置、历史、应用状态及知识库关联一次事务提交；注入真实数据库写入异常，确认原运行配置和关联完整保留。 |
| C03 | 同一应用同时发布，或发布期间更新草稿/取消发布 | 生命周期写入先锁应用行，再读取草稿与版本号；独立 Session/连接验证实际 PostgreSQL 锁等待及最终数据。连续发布保留原有新增版本行为，版本号分别为 1、2。 |
| C04 | 复制已发布应用 | 显式复制业务信息与深拷贝草稿，不复制 token、运行配置或会话；修改副本后原草稿和发布历史不变。 |
| C05 | 从实际内置模板创建应用 | 修正 draft_app_config_id 误写到 app_config_id，缺失模板返回 not_found；使用实际模板验证草稿关联与内容。 |
| C06 | 模型 parameters 为列表、轮数为布尔值、工具/工作流 UUID 非法 | 提前返回 validate_error，避免进入数据库或产生通用失败；5 组输入回归。 |
| C07 | 配置包含其他账号资源，或引用资源已删除 | 读取知识库、工具和工作流时限定账号；读取不再隐式改写快照或删除其他应用关联。发布和回退清理失效引用，历史快照保持不变。 |
| C08 | 获取、轮换 WebApp token 或取消发布 | 修正 token 持久化和 Service 数据库注入；生成/轮换在应用事务锁内执行，取消发布清空凭证，使用 secrets 生成随机字符。验证新凭证可用、旧凭证失效及取消发布后不可用；保持原登录保护。 |
| C09 | 删除带发布历史和知识库关联的应用 | 一次事务删除 App、AppConfig、AppConfigVersion 与 AppDatasetJoin；核对真实数据库无对应残留。 |
| C10 | 草稿引用从目录移除的 Provider/模型 | 捕获实际 NotFoundException，返回默认模型配置但不改写原草稿；2 项回归先失败后通过。 |

测试源码：

- [应用、配置、模板和凭证 HTTP 回归](../llmops-api/test/integration/handler/test_app_lifecycle_http_routes.py)
- [真实数据库发布竞争回归](../llmops-api/test/integration/test_app_lifecycle_concurrency.py)

### 验证与边界

- 首批新增应用回归：13 failed / 55 passed；修复和补充竞争/引用场景后 74 passed；模型目录失效回归补充后先 2 failed，再全部 **76 passed / 303 warnings**。
- 离线回归：**118 passed / 5 skipped / 8 warnings**。跳过的是需要真实付费 Provider 的 smoke 测试；警告主要为既有依赖弃用提示。
- 全部 93 个注册路由都有匿名拒绝矩阵以外的访问证据。路由访问仅作清单完整性检查，稳健性结论依赖上述状态、回滚与竞争断言。
- 新的事务回滚会正确撤销失败请求前未提交的测试数据；跨账号 HTTP 测试改为先提交账号归属设置，再发送请求，防止 fixture 数据随回滚消失。
- 标准入口 `sh scripts/test.sh` 跑通，测试 PostgreSQL 容器和网络已自动清理；未读取 `.env`，未调用真实外部模型或公网服务，未修改生产/开发数据库、前端或历史迁移，未提交或推送。
- 删除会话/消息/Thought 以及运行中 Agent 的收尾尚未验证，按计划在阶段 5 完成；本批不宣称应用删除后的全部运行数据已清理。
- 引用所属资源在其他事务中并发删除的完整一致性尚未覆盖，本批验证已删除引用的过滤；知识库跨存储删除和工作流状态竞争分别进入阶段 4/6。
- PostgreSQL 行锁只协调遵循该服务调用链的写入，未新增版本号唯一约束或客户端请求去重协议；不保证直接 SQL 写入的并发安全。配置读取默认模型仅是展示/解析回退，不代表真实 Provider 可用。

日志：`/private/tmp/trace-stage2-red.log`、`/private/tmp/trace-stage2-concurrency.log`、`/private/tmp/trace-stage2-model-red.log`、`/private/tmp/trace-stage2-final.log`、`/private/tmp/trace-stage2-unit-final.log`。XML 与逐路由测试映射保存在系统临时目录 `trace-robustness-baseline/`，重跑会覆盖。

下一阶段：验收后进入阶段 3，优先修复外部请求缺少超时、动态工具可选参数，并继续模型/工具/上传失败处理。

## 阶段 3 第一批：外部 HTTP 调用链

用户已验收阶段 2，明确暂不处理逻辑删除。本批不修改删除实现、不触碰前端，并保留开始时已有的 `internal/router/router.py` 未提交改动。

### 问题、修复和证据

- B04/B05：自定义工具省略可选参数被错误拒绝；自定义工具和 HTTP 节点没有 timeout。补可选默认值和 `(5, 30)` 连接/读取超时，响应在 finally/closing 中释放。HTTP 节点将 Pydantic HttpUrl 显式转为字符串传递给 requests。
- D01：GitHub 换 token、取用户、取邮箱请求缺少超时和显式关闭。现在每次请求都有超时，状态码校验或 JSON 解码失败也关闭响应。不自动重试授权码交换。
- D02：GitHub 无效 token 响应可能被原样拼入异常；非字典/非列表响应可能触发意外属性错误。现在校验响应形状、token 类型及邮箱条目，失败文案不回显上游响应。原来正常身份转换结果不变。
- D03：内置高德天气工具的 Session 和两次响应没有显式关闭，也没有超时。使用 ExitStack 登记资源清理，在成功、首请求失败、第二请求失败和 JSON 解码失败时均执行；原有天气字符串和失败提示不变。

回归源码：[外部 HTTP 边界](../llmops-api/test/internal/service/test_external_http_boundaries.py)。全部外部 HTTP 请求由 Fake 替换，断言调用次数、timeout、资源关闭及返回值，而非实际连接第三方。

### 兼容行为与测试结果

- 不改 API 路由、响应结构、错误码体系或 SSE 契约；没有新增自动重试。自定义工具仍返回上游文本；HTTP 节点仍返回 `text`、`status_code`，包括非 2xx 状态。节点/工具网络异常继续交给原有上层异常链路处理。
- 第一轮新测试 **22 failed / 118 passed**，修复并补充边界后 **145 passed**；天气工具补充回归先 **4 failed / 145 passed**，修复后全部离线 **149 passed / 5 skipped / 8 warnings**。
- HTTP 集成回归 **76 passed / 303 warnings**，独立 PostgreSQL 迁移正常，测试容器和网络自动清理。该集成结果验证核心 HTTP 修复；随后天气工具改动由离线 Fake 回归单独验证。
- 5 项跳过仍为真实模型 smoke 测试。未读取 `.env`，未访问真实模型、GitHub 或高德，不修改开发/生产数据库，未提交或推送。
- 日志：`/private/tmp/trace-stage3-http-red.log`、`/private/tmp/trace-stage3-weather-red.log`、`/private/tmp/trace-stage3-http-final.log`、`/private/tmp/trace-stage3-http-integration.log`。

### 尚未验证与后续批次

- requests 的连接/读取超时不等于整个请求或工作流总耗时上限；持续缓慢输出的服务、DNS 解析以及响应体内存上限尚未治理。真实供应商网络行为未联调。
- 上传文件大小/类型/文件名、COS 上传成功但数据库失败的补偿、SDK 超时与资源释放仍待检查。
- 模型工厂、Provider/结构化输出、其他 SDK 内置工具仍需专项审查；现有模型单元测试通过不代表阶段 3 完成。
- B09 启动时加载本地 Embedding 和 B10 Python 版本声明仍待后续处理。本批未改运行架构或基础设施。

本批验收后继续阶段 3 的上传调用链，再处理模型与 SDK 工具边界。

## 阶段 3 完整交付

用户随后要求连续完成整个阶段 3，不再在批次间停下验收。以下为第一批之外的审查、修复和证据；阶段 4 尚未开始。

### 已确认问题与修复

| ID | 原问题/复现条件 | 最小修复与验证 |
| --- | --- | --- |
| D04 | 上传大写图片扩展名被拒绝；文件名包含客户端路径、为空或超出数据库长度；直接 Service 调用可绕过大小校验 | 统一小写扩展名，保存最后一段文件名，校验名称长度/控制字符，最多读取 15MB+1 并拒绝超限。保留既有文档/图片扩展名白名单及 MIME 元数据；不将扩展名检查称为内容鉴定。 |
| D05 | COS 上传成功而数据库写入失败，遗留随机对象 | 数据库失败后仅补偿删除本次随机 key；清理失败记录 key 并保留原错误。Fake COS + 真实数据库插入异常验证无失败记录；上传自身失败不创建记录。COS timeout 30 秒、关闭 SDK 自动重试，不盲目重复上传。 |
| D06 | 删除自定义工具使用 `provider_id == provider_id` 等恒真条件，可删除所有账号的工具 | 明确限定 ApiTool.provider_id 和 account_id；真实数据库确认同账号其他提供者及其他账号工具仍存在。仅修正过滤条件，未改逻辑/物理删除方案。 |
| D07 | 工具提供者创建/更新多次提交，中途失败留下残缺提供者或丢失原工具 | 提供者和全部工具放入一次事务；更新/删除锁住提供者，创建/改名锁住账号后检查名称。真实数据库注入工具写入失败验证整体回滚；两个独立连接验证并发同名创建被拒绝、不同名创建成功，检查最终记录数量。无新迁移，不替代数据库唯一约束或保护绕过 Service 的直接 SQL 写入。 |
| D08 | 自定义 Schema 缺省 parameters 引发 KeyError，同路径 get/post 相互覆盖，嵌套类型错误成为通用失败 | 校验结构和 HTTP 地址、参数/路径占位符；保留同路径多个已有支持方法。参数名称禁止重复，路径参数必须必填。Pydantic 类型错误统一转换为既有 validate_error。仍只支持既有 get/post 子集，不宣称实现完整 OpenAPI。 |
| D09 | 数字 header/cookie 无法被 requests 发送，路径值可改变请求路径，固定 headers 可携带换行 | header/cookie 转字符串、路径参数 URL 编码、跳过 None 可选参数；固定请求头类型及换行校验。保留 localhost 和内网 URL 能力。 |
| D10 | NaN 绕过模型参数上下界，结构化输出尝试次数可为非整数 | 拒绝非有限浮点数和非正整数尝试次数。新增失败次数用例验证格式校验最多调用两次，超时和无关异常不重试；原 Provider 策略和已存在格式重试机制保留。 |
| D11 | 可见远程模型依赖 SDK 默认超时/重试，本地 Ollama 没有显式边界；旧 Service 默认模型类方法错误且绕过工厂 | OpenAI/DeepSeek/Kimi/豆包/智谱统一 60 秒请求超时、SDK 重试 0；Ollama 显式 client timeout 60。旧 Service 入口复用工厂与实例默认模型，仅无效配置回退。缺少可选 SDK 返回明确校验错误。 |
| D12 | Serper SDK 同步请求无 timeout，异步自有 Session 路径不检查 HTTP 错误 | 薄包装补同步 5/30 秒、异步总 35 秒边界及资源关闭，保持原结果解析。Fake 覆盖 HTTP、JSON、响应形状、超时和异步成功清理。 |
| D13 | DALLE 目录声明 style，但 SDK 的 run 不转发；默认 SDK 自动重试可能重复计费 | 显式转发已有 style/size 参数，验证目录选项，timeout 60 秒、重试 0。Fake 返回图像 URL 并检查实际参数；保留 openai_dalle 工具名与文本返回形式。 |
| D14 | DALLE/高德/Wikipedia 图标存放在 `_asset`，Service 只读取 `_assets` | 兼容两种现有目录；遍历全部 6 个内置 Provider 的目录、输入和实际图标文件验证。时间工具离线调用通过。 |
| D15 | 可选 DuckDuckGo/Wikipedia 依赖缺失时抛原始 ImportError | 转为说明缺少 ddgs/wikipedia 的既有校验异常；模拟缺失依赖回归通过。此修复不代表依赖已安装或真实工具调用可用。 |

### 全覆盖审查范围

| 调用链 | 证据/状态 |
| --- | --- |
| 模型目录、详情、图标，8 个 Provider、可见与隐藏模型 | 原有目录/工厂测试及本次参数边界回归；6 个可见 Provider 可离线构造，隐藏通义/文心受可选 SDK 限制。completion 是历史类，统一工厂仍按既有规则仅接受 chat。 |
| 结构化输出 json_schema/json_mode/function_calling/prompt | 审阅工厂策略、校验与有限重试；现有策略测试和新增错误类别/次数断言通过，无真实模型调用。 |
| 内置 Google、Time、DuckDuckGo、DALLE、高德、Wikipedia | 目录/输入/图标全部检查；Google、DALLE、高德 Fake 边界及 Time 本地调用通过；DuckDuckGo/Wikipedia 缺失依赖路径通过，实际 SDK 运行受限。 |
| 自定义工具 Schema、CRUD、动态参数、运行 HTTP | 输入边界离线回归及真实数据库事务/隔离/竞争回归通过。未启用硬编码示例 `api_tool_invoke`，该方法未注册路由。 |
| OAuth 跳转、身份获取、授权交换 | 阶段 1 身份/权限/事务回归加本阶段超时、异常关闭和响应形状回归；OAuth state/JWT 撤销仍按用户要求暂缓。 |
| 文件/图片上传、COS 下载 | 上传 Handler/Schema/Service/数据库 + Fake COS；下载使用同一 SDK timeout，沿用 SDK下载行为。真实 COS 上传/下载未调用。 |
| Embedding/FAISS 初始化、模型缓存发布 | 延迟初始化/并发/失败重试测试；全量集成工厂启动和迁移未触发本地模型加载。真实检索与向量一致性按阶段 4。 |

### 验证结果

- 新上传回归最初 **8 failed / 151 passed**；模型/启动回归最初 **11 failed / 164 passed**；Schema 回归最初 **8 failed / 175 passed**；新增数据库事务与删除隔离回归最初 **3 failed / 79 passed**。这些问题均已修复。
- 最终离线：**212 passed / 5 skipped / 8 warnings**。最终隔离 PostgreSQL 集成：**84 passed / 313 warnings**，全部现有迁移通过，临时测试容器和网络自动清理。
- 新增上传成功测试断言响应字段集合不变；已有 93 个注册路由的回归继续通过。路由访问不代表所有生产场景已验证。
- `git diff --check` 通过。未读取 `.env`，未访问真实模型/公网业务服务，未修改前端、生产/开发数据库或迁移历史，未提交或推送。保留用户原有 Router 改动及执行期间出现的 examples 目录。

代码证据：

- [上传单元回归](../llmops-api/test/internal/service/test_upload_robustness.py)
- [模型与启动边界](../llmops-api/test/internal/service/test_model_runtime_robustness.py)
- [自定义工具 Schema 与参数](../llmops-api/test/internal/service/test_api_schema_robustness.py)
- [内置工具 SDK 与目录](../llmops-api/test/internal/service/test_builtin_runtime_robustness.py)
- [上传与工具数据库状态](../llmops-api/test/integration/handler/test_tool_upload_robustness.py)
- [工具并发创建](../llmops-api/test/integration/test_tool_concurrency.py)

最终日志：`/private/tmp/trace-stage3-unit-final.log`、`/private/tmp/trace-stage3-concurrency.log`；最初失败日志对应 `trace-stage3-upload-red.log`、`trace-stage3-model-red.log`、`trace-stage3-schema-red.log`、`trace-stage3-tools-red.log`。后续重跑会覆盖临时 XML/routes.json。

### 受限项与未验证边界

1. 当前环境确认未安装 `ddgs`、`wikipedia`、`dashscope`、`qianfan`，仓库也未声明这些依赖。没有擅自升级/安装它们。DuckDuckGo、Wikipedia 和隐藏通义/文心的真实调用、SDK 超时与连接生命周期仍为受限项，不报告为已可用；第三方包装器不提供统一的可控传输接口，需要在启用对应 SDK 时单独验证。
2. 5 项真实模型 smoke 测试仍跳过；真实 Provider 行为、计费、断流、真实 GitHub/COS/高德/Serper 服务未联调。API 进程内线程不能强制终止任意 SDK；请求读取超时不是总执行时限。模型流生命周期继续由阶段 5 审查，不提前关闭仍在使用的 SDK 客户端。
3. COS 与数据库没有分布式事务：数据库回滚后对象补偿删除若也失败，日志记录 key 供清理；进程崩溃、上传响应丢失或数据库提交结果不确定仍可能残留对象/记录，不保证 exactly-once。未新增清理任务/状态表/基础设施。文件类型仍按既有扩展名检查，不保证内容与 MIME 一致；未增设文件内容扫描。
4. 外部 HTTP 响应体尚无统一大小上限，DNS/缓慢持续输出不受读取超时的总时长约束。保留内网调用能力，不新增 SSRF 地址封禁。
5. 修正 Python 声明和延迟初始化不等于全新机器部署已验证；首次检索仍需可信的本地 Embedding 与 FAISS 配套文件。FAISS 反序列化仍只用于仓库自身可信资产。

阶段 3 的代码加固、检查清单和当前环境可执行回归已完成；上述限制留给阶段验收，不默认为已解决。后续经用户确认进入阶段 4：知识库与索引一致性。

## 阶段 4 交付：知识库与索引一致性（2026-09-23）

本阶段保持已有物理删除语义；用户已要求暂不引入逻辑删除。本批没有修改 API 路由、成功响应字段、业务错误码、SSE 契约、迁移历史或基础设施。

### 已确认问题、最小修复与回归

| ID | 复现条件 | 修复与验证 |
| --- | --- | --- |
| E01 | 关键词表或向量库在禁用、失败或删除后存在滞后数据 | 全文检索在片段查询同时限定片段与父文档均为 completed 且 enabled；语义和混合检索在返回前也以 PostgreSQL 过滤候选。被过滤结果不再创建 DatasetQuery 或累加 hit_count。两项离线回归分别验证关键词和过期向量路径。 |
| E02 | Celery 重复投递同一 waiting 文档 | 以 PostgreSQL 行锁原子认领 waiting 文档并立即转为 parsing；非 waiting 或已删除文档跳过。真实测试库验证第二次 build 不会再次进入解析、切分、关键词和完成调用链。 |
| E03 | 新建文档入队失败，或启停/删除任务入队失败 | 创建文档、规则和位置号在同一事务中写入；入队失败将尚未处理的文档标为 error。启停入队失败回滚 enabled 状态并释放 Redis 锁；删除先入队，失败则保留主文档。任务参数统一序列化为 UUID 字符串。HTTP 回归检查入队失败后数据库状态。 |
| E04 | 删除文档的消息先被 Worker 消费，或索引任务滞后于删除 | 删除任务发现主文档仍存在会短暂重试，直到主记录提交删除；向量清理暂时失败同样有限重试。关键词表写入前检查知识库主记录，清理缺失关键词表不再自动创建孤立记录。回归覆盖已删除知识库的滞后关键词写入。 |
| E05 | 向量库清理失败时先删 PostgreSQL 主知识库 | 删除顺序调整为先删向量、再删派生 PostgreSQL 数据、最后删知识库及应用关联。向量失败向调用方返回 fail，主记录保留，用户可重试；真实数据库回归确认保留。 |
| E06 | 新增、编辑或删除片段后，文档汇总误加同知识库其他文档的片段 | 三处 character_count/token_count 聚合增加 document_id 限定；真实 HTTP 回归建立同知识库的另一文档片段，验证当前文档只统计自身。 |
| E07 | 部分向量批次失败时父文档仍错误显示 completed/enabled | 完成阶段统计 error 片段；存在失败时文档转 error、记录失败数量并禁用，成功时保持既有 completed 行为。 |

### 验证结果

- 新增检索离线回归 **2 passed**；Python `compileall` 与 `git diff --check` 通过。
- `sh scripts/test.sh` 在独立 PostgreSQL 容器中完成迁移和全部 HTTP 集成：**88 passed / 319 warnings**。测试容器、网络和测试数据均已自动清理。
- 集成回归覆盖文档入队失败、删除入队失败、片段汇总、重复任务认领、删除向量失败保留主记录以及滞后关键词任务；模型、Embedding、HTTP 和 Weaviate 均为 Fake 或未实际调用。未读取 `.env`，没有访问真实模型、公网、开发/生产数据库，未提交或推送。

代码证据：

- [检索可见性回归](../llmops-api/test/internal/service/test_retrieval_consistency.py)
- [文档与片段 HTTP 回归](../llmops-api/test/integration/handler/test_document_segment_http_routes.py)
- [索引重复投递与清理回归](../llmops-api/test/integration/test_dataset_indexing_consistency.py)

### 受限边界

1. Celery 没有 outbox 或幂等任务记录。当前用 waiting 状态认领和删除短暂重试减轻重复/先后竞态，但进程在数据库提交与消息投递之间崩溃仍可能留下 error 文档，需要用户重新提交；没有引入新基础设施。
2. PostgreSQL、Redis 关键词表和 Weaviate 不是分布式事务。向量删除失败时保留主记录可重试；向量成功但后续 PostgreSQL 提交失败仍需要重试清理。真实 Weaviate 和多 Worker 的并发行为未联调，不将 Fake 验证等同于 exactly-once。
3. 文档执行期间被删除、启停和索引完成的更深层并发时序没有新增删除中间状态；现有物理删除模型缺少可供任务协作的 lifecycle 字段。若后续需要严格的可恢复删除，应先由用户确认逻辑删除或删除状态与迁移方案。
4. 本批对失败片段只验证父文档不被错误标完成；针对单个向量节点已经写入但事务随后失败的补偿删除仍受 Weaviate 可用性约束，未增加扫描或补偿任务。

阶段 4 的范围内问题已修复并完成隔离验证，以上架构限制不视为已解决。下一阶段为对话、Agent 与流式持久化。

## 阶段 5 交付：对话、Agent 与流式持久化（2026-09-23）

本阶段先阅读并保持 [Agent 流事件契约](contracts/agent-stream-events.md)；不改变 SSE 事件名、字段、HTTP 状态码、API 返回结构、数据库迁移或运行架构。

### 已确认问题、最小修复与回归

| ID | 复现条件 | 修复与验证 |
| --- | --- | --- |
| F01 | 调试、公开 API 或辅助 Agent 的客户端在首个 SSE 片段后断连 | 原实现只在 Generator 自然结束后启动保存线程，断连会跳过保存。现在捕获 Generator 结束路径后在后台继续消费同一个 Agent iterator，直到队列终止，再保存已收集的步骤、部分回答、错误/停止状态及用量。三条调用链均有离线回归，断连后断言只保存一次。 |
| F02 | 公开 API 创建 Agent 时错误标记为 debugger | 改为 `service_api`，使任务归属、日志和未来停止语义与实际入口一致；SSE 字段不变。持久化线程保留 UUID 参数，不再先转字符串后写数据库。 |
| F03 | 旧版 `/apps/<id>/debug` 后台图异常或发送普通字符串事件 | 图执行使用 finally 始终放入结束标记，异常发送既有 `error` SSE；修正字符串事件被读取 `.value` 导致消费失败的问题，并为队列等待增加 600 秒 timeout 终止事件。HTTP 回归实际消费正常空流和异常流。 |
| F04 | 辅助会话惰性创建路径遗留调试 `print` | 移除请求路径的控制台输出，避免内部会话 ID 和状态进入标准输出。 |

### 验证结果

- Agent 终止、用量、持久化、会话及三种 SSE 入口离线回归：**33 passed**。
- `sh scripts/test.sh` 完成独立 PostgreSQL 迁移与 HTTP 集成：**88 passed / 320 warnings**；旧调试入口的正常和异常流均被实际消费。
- 测试中模型、工具、Redis、后台线程均为 Fake 或同步替身；未读取 `.env`，未调用真实模型/公网/生产数据，测试容器和网络自动清理，未提交或推送。

代码证据：

- [调试流与断连保存](../llmops-api/internal/service/app_service.py)
- [公开 API 流](../llmops-api/internal/service/openapi_service.py)
- [辅助 Agent 流](../llmops-api/internal/service/assistant_agent_service.py)
- [Agent 用量与断连回归](../llmops-api/test/internal/service/test_agent_usage_responses.py)
- [旧调试入口 HTTP 回归](../llmops-api/test/integration/handler/test_app_runtime_http_routes.py)

### 受限边界

1. 断连后后台排空线程最多受 AgentQueueManager 的现有 600 秒监听限制；不会取消已发送的模型或工具请求，也不能强制终止任意 SDK 调用。
2. 队列仍在 API 进程内。跨进程/多 Worker 重连、`Last-Event-ID` 重放和进程崩溃后的恢复没有实现；客户端断网、浏览器代理和真实模型断流没有联调。
3. PostgreSQL 持久化没有 outbox。进程在 Agent 完成与后台保存开始之间崩溃时仍可能缺少最终记录；用量继续按供应商实际返回数据结算，异常终止的 `usage.complete=false` 和 `total_price=null` 不能视作免费或最终账单。
4. 辅助会话与调试会话的惰性创建仍是既有模型属性行为；本阶段没有引入跨请求唯一约束或会话逻辑删除，删除策略按用户此前要求暂不改造。

阶段 5 的范围内问题已修复并完成隔离验证，以上限制不视为已解决。下一阶段为工作流与 AI 辅助功能。

## 阶段 6 交付：工作流与 AI 辅助（2026-09-23）

本阶段不改变既有工作流路由、草稿/发布响应结构或 `workflow` SSE 事件名。调试执行失败时仅在该事件补充 `status` 与通用 `error`，不删除或改写原有成功节点字段；也不新增代码沙箱、迁移或基础设施。

### 已确认问题、最小修复与回归

| ID | 复现条件 | 修复与验证 |
| --- | --- | --- |
| G01 | 工作流节点输入引用自身输出 | 前置节点计算原先把目标节点自身加入可引用集合，配置会通过但运行时无法取得值。现在只返回真正祖先节点；验证 start→template→end 的合法引用可串行执行，自引用被明确拒绝。 |
| G02 | 已成功调试的工作流在下一次调试运行失败 | 调试失败原先只把 WorkflowResult 标为 failed，仍保留 `is_debug_passed=true`，且 SSE 没有失败结果。现在记录失败状态、重置发布门槛，并发送既有 `workflow` SSE 的失败状态和通用错误字段。 |
| G03 | 自定义工具节点在运行时按 provider/name 查询工具 | 节点构建阶段增加 workflow account_id，并再次限定 ApiTool.account_id；避免配置以外的运行时查询越过所属账号边界。 |
| G04 | 旧代码路径在辅助会话创建时写入 stdout | 该输出已在阶段 5 删除；本阶段确认不把代码节点的 AST 形式校验误记为隔离执行。 |

### 检查与验证

- 审查 Start、End、LLM、模板转换、工具、知识库检索、HTTP、代码八类节点，以及 WorkflowConfig 的节点、边、连通性、环路和变量引用校验。
- 工作流图、运行时失败、工具账户传递及 LLM 节点离线回归：**8 passed**。
- `sh scripts/test.sh` 在独立 PostgreSQL 中迁移并通过 HTTP 集成：**88 passed / 320 warnings**。所有模型、工具、检索与 HTTP 依赖均为 Fake 或未调用。
- 未读取 `.env`，没有访问真实模型、公网、开发/生产数据库；未修改迁移、未提交或推送。

代码证据：

- [工作流运行图](../llmops-api/internal/core/workflow/workflow.py)
- [变量引用校验](../llmops-api/internal/core/workflow/entities/workflow_entity.py)
- [调试失败收尾](../llmops-api/internal/service/workflow_service.py)
- [工作流回归](../llmops-api/test/internal/service/test_workflow_robustness.py)

### 受限边界

1. CodeNode 仍在 API 进程内执行可信 Python；AST 仅限制顶层结构，不能隔离文件、网络、内存或无限循环，也不能强制终止任意 Python 代码。按本轮范围不新增沙箱或进程隔离。
2. LLM、工具、知识库检索和 HTTP 节点的真实供应商行为未联调；HTTP 节点沿用阶段 3 的超时和关闭处理，但没有总工作流墙钟时限、响应体上限或跨节点取消协议。
3. 草稿保存保持宽松，允许未完成图；调试/发布时 WorkflowConfig 执行完整图校验。并发草稿编辑、发布与调试之间没有新增版本号或 outbox，直接 SQL 写入也不受 Service 约束。
4. AI 提示词优化的流只有既有 `optimize_prompt` 片段事件，没有独立终止/错误事件契约；建议问题沿用 ConversationService 的结构化输出、有限格式重试和空列表回退。本阶段未改变其接口。

阶段 6 的范围内问题已修复并完成隔离验证，以上限制不视为已解决。下一阶段为统计、缓存与总体验收。

## 阶段 7 交付：统计、缓存与总体验收（2026-09-23）

本阶段不改变统计路由、成功响应字段、费用存储精度或缓存键。数据库的货币值继续使用 `Numeric`/`Decimal` 累积，概览与趋势在 JSON 边界输出 `float`，以保证图表响应可序列化。

### 已确认问题、最小修复与回归

| ID | 复现条件 | 修复与验证 |
| --- | --- | --- |
| S01 / B08 | Redis 可读但缓存内容损坏，或统计重算完成后的 `setex` 写入失败 | 缓存读取/解析异常继续重算；写入异常现在记录服务端日志并直接返回已计算的统计，缓存故障不再将成功计算变为接口失败。单元测试覆盖损坏缓存和写入故障，HTTP 集成测试确认成功响应。 |
| S02 | 空消息、零会话或总耗时为零 | 概览、环比和七日趋势均返回零值，不发生除零或 JSON 编码失败。 |
| S03 | 消息费用为 `Decimal` | 费用概览和趋势均在响应边界转换为 `float`；回归以 `Decimal("0.00125")` 验证结果并执行 `json.dumps`。 |

### 最终验证

- 新增统计缓存与数值回归：**2 passed**。
- 全部离线单元测试：**223 passed / 5 skipped / 8 warnings**。跳过项是显式要求 `RUN_LLM_SMOKE_TESTS=true` 的付费模型 smoke 测试。
- 独立 PostgreSQL 迁移及 HTTP 集成测试：**89 passed / 323 warnings**。测试容器已由脚本清理。
- 未读取 `.env`，未访问真实模型、公网、开发/生产数据库；未新增迁移、未提交或推送。

代码证据：

- [统计与缓存降级](../llmops-api/internal/service/analysis_service.py)
- [统计 HTTP 回归](../llmops-api/test/integration/handler/test_security_http_routes.py)
- [统计数值回归](../llmops-api/test/internal/service/test_analysis_robustness.py)

### 最终受限项

1. Redis、Celery、Weaviate 及真实模型/工具供应商均未做真实服务故障或竞争联调；隔离测试使用本地 PostgreSQL 与 Fake 或不可连接的外部依赖。
2. 统计费用展示的是已持久化的已知费用；单次 Agent 调用是否完整仍由 `Message.usage.complete` 和 `price_status` 表示，现有统计响应没有单独的“未结算费用”字段。新增该字段会改变接口契约，未在本轮实施。
3. 阶段 1 明确暂缓的 JWT 撤销、令牌版本和 OAuth `state`，以及阶段 6 的可信代码进程内执行限制，仍按原记录保留。

全部计划阶段已完成；以上受限项不视为已解决。

## 新增 WebApp 与会话模块增量验收（2026-09-24）

用户新增 WebApp 对话、会话列表以及通用会话读写路由后，沿用原计划的权限、状态、异常、持久化和 SSE 验收方法。本批保留既有路由、成功响应结构、事件名和逻辑删除语义，不涉及前端、迁移、真实模型或公网调用。

| 问题与复现 | 修复及证据 |
| --- | --- |
| WebApp 新建对话使用不存在的 `appid` 字段及 `app.conversation` 属性；运行配置调用参数不符，模型、检索和会话保存依赖未注入 | 改用 `app_id`、实际会话记录和已发布运行配置，补齐注入。真实 HTTP + 独立 PostgreSQL + Fake Agent 验证新会话、复用、回答和步骤持久化。 |
| WebApp 对话函数本身是生成器，归属校验推迟到 SSE 开始后，错误无法按既有业务错误返回；请求身份代理也可能在流消费时失效 | 在返回生成器前完成查询、归属检查与准备，并传入具体账号对象；跨账号和已删除会话在 SSE 启动前拒绝。断连后排空同一个 Agent iterator 并保存结果。 |
| WebApp 会话列表查询调用不存在的 `.filte`；会话消息 Handler 用请求 Schema 当作响应 Schema；时间游标调用了错误的 `datetime` 导入 | 修正查询和序列化，实库验证置顶列表、消息分页、响应字段与时间游标；过大时间戳返回校验错误。 |
| 新会话在模型或工具准备失败前已创建空会话/消息 | 将新会话和消息创建移到准备完成后；Fake 模型故障回归确认失败响应不留下 WebApp 会话或消息。 |
| 会话消息分页只按 `conversation_id` 过滤，删除只验证会话 ID，数据关联不一致时可能返回或删除其他应用/调用来源的消息 | 查询和删除同时核对应用 ID、调用来源与创建者；真实数据库回归注入关联不一致的消息，确认不可读也不可删。 |
| 路由注入将统计 Handler 误导入为 Service | 恢复 `AnalysisHander` 路由类型，现有统计 HTTP 回归继续通过。 |

验证：离线单元基线 **223 passed / 5 skipped**；新增模块后独立 PostgreSQL HTTP 回归 **93 passed / 396 warnings**，测试脚本已清理容器。全部新增路由有 HTTP 访问证据；新模块的模型和 Agent 行为由 Fake 代替。真实 Redis 停止信号、真实模型及跨进程断连恢复仍未联调，不视为已验证。

## 四个会话入口统一加固（2026-09-24）

本批由用户明确授权实现，保留四个业务入口和鉴权规则，抽取公共准备与执行逻辑；不修改路由、成功响应字段、SSE 事件名、OpenAPI 非流式响应或逻辑删除策略。

| 状态 | 问题与复现条件 | 修复与证据 |
| --- | --- | --- |
| 已修复、已验证 | 四个入口重复合并、编码、排空和保存；单独修改容易造成终止或用量行为分歧 | [ChatRuntime](../llmops-api/internal/service/chat_runtime.py) 共用流式生命周期及保存参数快照；终止处关闭 iterator，只安排一次保存。保留辅助 Agent 的专用模型、工具及 SSE 空白格式，OpenAPI 保留 EndUser 和非流式输出。 |
| 已修复、已验证 | 非预期 iterator 异常或无终止事件的流可能留下正常状态的部分消息 | 公共执行层补充既有 error 事件，正常模型 error 原样传递；[运行时回归](../llmops-api/test/internal/service/test_chat_runtime.py) 验证四类终止、断连、缺失终止、异常、关闭失败、线程启动失败及快照隔离。 |
| 已修复、已验证 | 调试、辅助 Agent、OpenAPI 在模型准备失败前已创建消息；调试和辅助入口校验延迟到生成器消费 | 请求内完成准备后创建消息，之后返回公共生成器。Fake 模型准备失败回归确认不创建 Message；既有会话属性和 OpenAPI EndUser/Conversation 的创建时机未扩展重构。 |
| 已修复、已验证 | WebApp 访问者不是应用所有者时，知识库检索误用访问者账号 | 公共应用准备函数明确 resource_owner_id 与 operator_id；[真实 HTTP 与 PostgreSQL 回归](../llmops-api/test/integration/handler/test_web_app_conversation_robustness.py) 验证资源使用应用所有者、任务使用访问者、消息和会话仍属于访问者，新建/复用/断连均实际保存。 |
| 已验证 | 原有返回和用量兼容性 | [入口回归](../llmops-api/test/internal/service/test_agent_usage_responses.py) 检查调试、WebApp、OpenAPI 流式/非流式字段、部分结果、用量与保存参数，辅助 Agent 断连仍保存停止状态；未知用量不会因正常终止被标记为完整结算。 |

最终验证：`robustness_baseline.py unit` **245 passed / 5 skipped / 8 warnings**；`sh scripts/test.sh` **94 passed / 409 warnings**，隔离 PostgreSQL 容器已清理。5 个跳过项为付费模型 smoke test；警告为现有依赖弃用提示。JUnit 证据位于系统临时目录 `trace-robustness-baseline/unit.xml` 与 `integration.xml`。`git diff --check` 通过。

受限：真实供应商、Redis/Weaviate 运行故障与多进程恢复未验证；HTTP 持久化测试使用同步线程替身和独立测试事务，不作为真实数据库线程竞争证据。后台保存仍沿用现有进程内线程，不保证进程退出或数据库不可用时可靠投递；本批不新增持久化任务队列或保存重试。尚未消费就被丢弃的响应不会启动 Agent，但已创建的消息不会自动补写终止状态。

已更新 [架构说明](architecture.md#agent-与-sse-数据流) 和 [SSE 契约](contracts/agent-stream-events.md)。本进度文件仍受现有 `docs/` 忽略规则影响，未强制添加到 Git；未读取 `.env`，未访问开发/生产数据或付费模型，未提交或推送。
