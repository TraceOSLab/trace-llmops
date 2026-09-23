# 可直接保存的工作流测试 JSON

本目录的 `01` 至 `08` 是 8 份独立工作流，顶层都是 `nodes`、`edges`，可以直接作为工作流的 `draft_graph` 保存。不需要运行生成脚本或启动额外的本地测试服务，也没有 API 提供者 ID 占位符。

模型沿用 `deepseek / deepseek-v4-flash`，知识库沿用 `a07e38ec-8c45-46d1-89e5-cd29643088aa`。工具节点使用项目已有的 `time/current_time`，不需要第三方工具密钥。HTTP 使用 JSONPlaceholder 的小型公开测试数据。

## 工作流清单

建议按编号从基础功能测到完整链路；每个文件创建为一个独立工作流，便于定位问题。

| 文件 | 建议名称 / tool_call_name | 节点数 | 测试重点 | 运行依赖 |
| --- | --- | --- | --- | --- |
| [01-basic-types.json](01-basic-types.json) | 基础类型与金额计算 / `test_basic_types` | 4 | string、int、float、boolean，可选参数，常量，代码，模板，跨节点引用 | 无外部服务 |
| [02-parallel-join.json](02-parallel-join.json) | 并行分支汇合 / `test_parallel_join` | 7 | 三路分支、不等长分支等待、内置时间工具、结果汇合 | 本机时间工具 |
| [03-http-query.json](03-http-query.json) | HTTP参数与响应解析 / `test_http_query` | 5 | GET query、header、单条数据解析、状态码、输入范围校验 | 公网 HTTP |
| [04-http-not-found.json](04-http-not-found.json) | HTTP 404业务检查 / `test_http_not_found` | 4 | 非200响应、预期404、保留错误响应摘要 | 公网 HTTP |
| [05-llm-extraction.json](05-llm-extraction.json) | 模型结构化抽取 / `test_llm_extraction` | 5 | 提示词、模型调用、JSON解析、字段类型、缺失信息 | 一次 DeepSeek 调用 |
| [06-dataset-retrieval.json](06-dataset-retrieval.json) | 知识库独立检索 / `test_dataset_retrieval` | 4 | 真实召回、空结果观察、字符数统计、上下文截取 | 当前知识库和检索服务 |
| [07-rag-answer.json](07-rag-answer.json) | 知识库问答 / `test_rag_answer` | 7 | 检索→模板→模型，答案与依据对照 | 知识库、一次 DeepSeek 调用 |
| [08-comprehensive.json](08-comprehensive.json) | 综合节点测试 / `test_comprehensive` | 10 | 全部8类节点、三路汇合、模型JSON、任务字段一致性 | 公网 HTTP、知识库、一次 DeepSeek 调用 |

`08-comprehensive.json` 就是这次整理的完整工作流。`after_sales/` 是此前依赖本地固定服务的方案，本轮在你自己的系统中测试时使用上表这 8 份即可。

## 保存与调试

若你通过现有接口操作：

1. 在当前账号创建工作流，填写上表的名称、英文名称及你已有的图标等基础资料。
2. 将对应 JSON 的完整内容作为 `POST /workflows/{workflow_id}/draft-graph` 的请求体，直接传 `nodes`、`edges`，不需要外层包装。
3. `POST /workflows/{workflow_id}/debug` 的请求体只放测试输入字段。

若你直接操作数据库，这些文件对应工作流记录的 **draft_graph 字段**，不是整条数据库记录。工作流的账号归属、名称等其他必填字段仍由你创建记录时填写。本轮只新增了示例文件，没有写入数据库或发布工作流。

每份工作流的多组测试输入与预期结果在 [cases/](cases/) 下的同名文件中。调试时只复制其中的 `inputs` 对象，不要把整条 case 或整个 cases 文件作为调试请求体。

### 第一轮输入

**01 基础类型：**

```json
{"product":"测试键盘","quantity":2,"unit_price":99.5,"vip":true}
```

预期 `subtotal=199.0`、`total=179.1`、`discount=0.9`、`note="无备注"`。布尔值传 JSON 的 `true` / `false`，不要传字符串。把数量改成 `0` 应在代码节点失败。

**02 并行汇合：**

```json
{"text":"  workflow  ","number":7}
```

预期 `cleaned="workflow"`、`length=8`、`squared=49`，时间非空；汇合模板应拿齐三个分支的结果。

**03 HTTP参数：**

```json
{"todo_id":1}
```

预期 `task_id=1`、`completed=false`、`http_status=200`。请求带 `id` query 参数限制为一条数据，不拉取整个待办列表；也可以改为 `2` 检查参数是否真的传到了 HTTP 节点。输入范围是 1 至 200。

**04 HTTP 404：**

```json
{}
```

预期 `http_status=404`、`expected_error_observed=true`，并正常到达结束节点。网络不可达或超时不属于预期的404业务响应。

**05 模型抽取：**

```json
{"text":"联系人姓名：张三；邮箱：zhangsan@example.com。"}
```

预期 `name="张三"`、`email="zhangsan@example.com"`、`format_valid=true`。将文本改为“今天下午三点开会。”时，姓名和邮箱应为空字符串。`format_valid` 只验证JSON字段结构，内容正确性要对照输入检查。

**06 独立检索、07 知识库问答：**

```json
{"query":"替换为当前知识库中确定存在的一个具体问题"}
```

这里需要你选一个已知问题，因为当前知识库的实际内容未被本轮读取。06 看返回的 `context` 是否相关，07 对照 `answer` 和 `context`，检查事实与引用有没有依据。检索节点虽然不调用聊天模型，但仍可能调用当前配置的 embedding 服务。

**08 综合测试：**

```json
{"query":"请结合知识库介绍一个有依据的知识点，并说明示例待办是否完成。"}
```

预期 `task_id=1`、`completed=false`、`http_status_code=200`、`passed=true`，`current_time` 非空。可以把问题换成知识库中你熟悉的具体主题，同时要求说明示例待办状态。

## 如何判断测试结果

- 正常运行时，各节点各有一次结果，最后是结束节点。并行分支事件的先后顺序不固定，应按节点 ID 或标题辨认。
- 03 和 08 会检查 HTTP 状态与 JSON 字段；04 则专门验证404是可读取的业务结果。公开接口的可用性仍受本机网络影响。
- 05 的 `format_valid` 和 08 的 `passed` 为 `false` 时，查看 `validation_error` 与原始模型输出。图运行成功不代表这两个检查通过。
- 06 的 `has_context=true` 只表示返回文本非空，不证明相关性。检索 `k=2`、阈值 `0.3`；06、07、08 将下游上下文限制为1200字符，并输出截断标记。检索节点自身的运行记录仍可能包含较长的原始结果。
- 08 模板最多使用问题的前500字符。05和07对过长输入直接抛错，适合测试输入边界。
- 当前调试服务捕获运行异常后不发送明确的失败 SSE 事件；非法输入等失败场景可能表现为流提前结束。不能只凭 HTTP 200 或连接结束判定成功，应检查是否到达结束节点。

这些图覆盖现有8类节点，但不绑定自定义 `api_tool`，因为新工具需要你账号内真实的 provider ID；也不引入当前模块没有的条件分支或循环节点。03 / 04 专门覆盖 HTTP GET，未覆盖所有 HTTP 方法。

## 本轮验证范围

8份图均通过现有 `WorkflowConfig` 的结构、节点引用和无环图校验；代码节点通过语法检查，模型参数通过本地模型目录校验。另完成12个离线场景：01 / 02共6个真实图执行用例，以及模型输出校验代码的6个正反例。内置时间工具运行时使用真实实现，初始化时绕过了业务应用的注入绑定。

未运行付费模型、真实知识库、数据库导入或这批图的公网 HTTP 请求。综合图使用的 `/todos/1` 在上一轮已单独返回过正常的小型JSON，但这不能代替你环境中的完整链路验证。
