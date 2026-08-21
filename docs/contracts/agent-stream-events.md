# Agent 流式事件现状（契约草案）

> 本文记录当前代码行为和未来前端需要关注的兼容面，不代表已经实现了版本化 `StreamEvent`、统一编码器、`sequence` 或事件重放。

## 传输格式

流式接口返回 UTF-8 编码的 Server-Sent Events，`Content-Type` 为 `text/event-stream`。当前 Agent Stream 的实际格式类似：

```text
event: QueueEvent.AGENT_MESSAGE
data: {"event":"agent_message","id":"...","conversation_id":"...","message_id":"...","task_id":"...","thought":"...","observation":"","tool":"","tool_input":{},"answer":"Hello","latency":0.12}

```

当前代码由各 Service 手写 SSE 字符串。`app_service.py` 和 `openapi_service.py` 直接把 `QueueEvent` 放入 f-string，因此 `event:` 可能是 `QueueEvent.AGENT_MESSAGE`，而 JSON 中的 `event` 是 `agent_message`；部分直接使用普通字符串的调试代码则不会出现这个前缀。当前既没有统一模型，也没有契约测试强制二者一致。

## 公共字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | UUID | 稳定的事件/步骤标识；同一回答步骤的 Token Chunk 共用该值。 |
| `event` | string | 事件判别字段，同时也是 SSE 事件名。 |
| `task_id` | UUID | Agent 任务 ID。 |
| `conversation_id` | UUID | 当前会话 ID；调试与公开对话流中存在。 |
| `message_id` | UUID | 当前消息 ID；调试与公开对话流中存在。 |
| `end_user_id` | UUID | 公开应用对话中的终端用户 ID。 |

`version`、`sequence`、`created_at` 和 `trace_id` 是候选目标字段，目前代码尚未发送。

## Agent 事件

| 事件 | 用途 | 关键字段 |
| --- | --- | --- |
| `long_term_memory_recall` | 已加载长期记忆。 | `observation` |
| `agent_thought` | 模型产生工具调用思考。 | `thought`, `latency` |
| `agent_message` | 流式回答片段。 | `thought`, `answer`, `latency` |
| `agent_action` | 已调用工具。 | `tool`, `tool_input`, `observation` |
| `dataset_retrieval` | 已完成知识库检索。 | `tool_input`, `observation` |
| `ping` | 保持空闲连接。 | 无事件专属字段 |
| `agent_end` | 正常终止。 | 无 |
| `stop` | 用户主动停止。 | 无 |
| `timeout` | 服务端超时终止。 | 无 |
| `error` | 异常终止。 | `observation` |

设计目标是一个任务只发送一个终止事件，并且终止后不再发送 Frame。当前 `AgentQueueManager.listen()` 的心跳、超时和停止检查位于 `finally` 中，这一不变量尚无契约测试保证；修改前应先补测试，不要直接假设其行为正确。

## 其他流式事件

- `optimize_prompt` 携带 `optimize_prompt` 文本片段。
- `workflow` 直接在顶层携带当前 Workflow Node 的结果字段。

## 后续兼容原则

- 在前端开始消费前，应把现有事件名和顶层字段视为待确认的兼容面。
- 正式冻结契约前，应先决定是否把 SSE `event:` 统一为 `QueueEvent.value`，并通过测试保证它与 `data.event` 一致。
- 引入正式契约时优先增加字段，不要无过渡地重命名或删除现有字段。
- 修改字段类型或终止语义时，应明确版本和迁移方式，并增加普通回答、工具调用、检索、停止、超时、异常、心跳与断连测试。
- 由于 Agent 事件使用进程内 Queue，目前不支持通过 `Last-Event-ID` 重连，也不支持服务端重放。
