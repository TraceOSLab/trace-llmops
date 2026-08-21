# LLMOps API 协作指南

## 分层边界

- Handler 负责验证 HTTP 输入、调用 Service 和序列化响应。
- Service 负责业务规则、权限检查和事务编排。
- Model 只定义持久化结构。Agent、Workflow、检索、工具和模型 Provider 的运行时逻辑放在 `internal/core/`。
- Extension 负责初始化 Flask 集成；不要绕过现有 Factory 和 Injector 注入关系隐式创建应用。

## Python 约定

- 新增 Core 实体和类型化运行时契约时使用 Pydantic v2。
- 保持现有 Flask-WTF 和 Marshmallow 接口兼容；不要顺带批量迁移 Schema 框架。
- 类型应尽量明确；Pydantic 可变字段使用 `default_factory`。
- 保持现有代码风格，不要格式化无关文件，也不要为了“更现代”而批量重写旧代码。

## Agent 与流式事件

- 当前 SSE 字符串分散在多个 Handler/Service 中，尚未建立统一编码器和正式版本化契约。不要把目标设计描述成已经实现。
- 修改事件名、字段、心跳或终止行为前，先列出受影响的生产方和消费方，再同步更新 `docs/contracts/agent-stream-events.md`。
- 当前 Agent Queue 只存在于单个 API 进程内，Redis 仅保存任务归属与停止标记；不支持多 Worker 共享、恢复或重放。
- Redis Streams、统一 `StreamEvent` 和 Agent 迁移到 Celery 都是候选演进方向，除非用户明确要求，否则只讨论、不实现。

## Celery 与数据库不变量

- 新任务只向 Celery 传递 ID 和基础类型，在任务内部重新加载 ORM 状态；不要顺带改造既有任务。
- 任务设计要考虑重试和重复投递；若有意保留非幂等行为，必须记录原因。
- 数据库变化要新增迁移，不要编辑 `internal/migrations/versions/` 下已有文件。
- 新增单元测试优先使用 Fake 并保持离线。现有 Handler 测试仍依赖真实数据库，不要假设测试已经完成分层。
