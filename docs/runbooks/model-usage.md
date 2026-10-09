# Agent 的 Token 和费用统计

本实现沿用 `FunctionCallAgent → AgentThought → ConversationService → Message/MessageAgentThought`，把本地重新分词替换为供应商返回的用量。没有引入全局 callback 或独立计费服务。

## 开始使用

1. 先对开发数据库运行新增迁移 `b739fd026a81`。VS Code 打开 `llmops-api/`，执行已有 `db upgrade` Task；终端等价命令是在该目录执行 `uv run flask --app app.http.app:create_app db upgrade`。
2. 重新启动 `Development (Flask + Celery)`。
3. 使用已有应用调试或公开 API。查看回答末尾空 `agent_message` 的单次调用 `usage`，以及 `agent_end` 的汇总。历史消息中也会返回统计。

迁移给 `message` 和 `message_agent_thought` 添加 JSONB `usage`，并将单价、换算乘数、总价扩大为 `Numeric(18,10)`，使 `0.000001` 的单位乘数和小额费用不会被原来的精度截掉。历史数据保留，已有迁移不变。代码检查不会自动运行真实数据库迁移；需确认目标是开发库后再运行 Task。

## 代码阅读顺序

- `internal/core/language_model/providers/*/chat.py`：DeepSeek、GLM、豆包开启流式 usage，保留缓存原始字段。
- `internal/core/language_model/usage.py`：统一用量、校验计数、Decimal 计价。
- `internal/core/agent/agents/function_call_agent.py`：每次调用结束后结算一次。取最后一个用量快照，避免累计型 chunk 相加。
- `internal/core/agent/usage.py`：事件合并、跨工具调用轮次汇总及 SSE 序列化。
- `internal/service/conversation_service.py`：按稳定步骤 ID 保存明细和消息总计；重复保存同一步骤更新已有行。

Manager 只负责创建模型并传入配置中的 provider/model 身份。`get_pricing()` 保留为固定价格的兼容入口；完整计价通过 `collect_usage()`，因为缓存、阶梯和峰谷价格无法由三个固定数表达。

## 价格配置

价格放在每个模型 YAML 的 `metadata.pricing`，金额使用带引号的十进制字符串。`unit` 是**乘数**：`"0.000001"` 表示每百万 token 的单价。

```yaml
metadata:
  pricing:
    currency: CNY
    input: "2"
    output: "8"
    cache_read: "0.2"
    unit: "0.000001"
    schedule: flat
    checked_at: "2026-09-18"
    source: https://example.com/official-pricing
```

以上是教学算例，不是任何模型的当前报价。输入 1000、其中缓存命中 800、输出 200，则费用为 `(200×2 + 800×0.2 + 200×8) × 0.000001 = 0.00216 CNY`。推理 token 已属于输出，不能再加一次。未声明 `cache_read` 的固定价配置表示输入统一计价；有缓存优惠却未取得命中量时，费用返回未知。

阶梯价使用 `tiers`，按输入总量（含缓存）依序选择第一个 `max_input_tokens` 大于等于输入量的档位，边界单位是 token。不要把各档累进相加。超出最后一个已配置档位时返回 `missing_pricing`，不沿用起步价。

```yaml
metadata:
  pricing:
    currency: CNY
    unit: "0.000001"
    tiers:
      - max_input_tokens: 32000
        input: "3.2"
        output: "16"
        cache_read: "0.64"
```

当前内置费率于 2026-09-18 核对：

- DeepSeek V4 Pro：高峰输入/输出/缓存命中为 9/27/0.30 元每百万 token。V4 Flash 旧名按 Flash 为 2/8/0.04；`schedule=deepseek_peak` 在北京时间工作日 09–12、14–18 使用高峰价，其余半价。以调用开始时间选择时段，跨时段调用的最终账单仍以供应商为准。[官方价目表](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- GLM-5.2：输入/输出/缓存命中为 8/28/2 元每百万 token。[官方价目表](https://docs.bigmodel.cn/cn/guide/start/pricing)
- 豆包 Seed 2.0 Pro / Lite：仅配置已核对的输入不超过 32000 token 的档位，分别为 3.2/16/0.64 和 0.6/3.6/0.12。更长请求仍统计 token，但费用未知，需按账号使用的方舟模型版本补齐对应 `tiers`；不把扣子等其他渠道的费率自动当作方舟长输入价。[方舟产品价目表](https://www.volcengine.com/product/doubao/)、[官方短输入档位参考](https://www.volcengine.com/docs/84458/1585097)

其他模型没有配置价格时仍可记录返回的用量，费用标为未知；免费模型须明确配置输入/输出为零。价格不是运行时联网抓取的，调整 YAML 只影响以后调用，已保存的费用和快照不重算。当前金额仅为推理 token 费用，不含缓存存储时长、工具服务费、赠送额度、套餐折扣和汇率换算。

## 未知和异常

- `source=missing`：没有收到可用的供应商用量；不会拿 GPT 分词器补成“实际用量”。
- `price_status=missing_pricing`：价格未配置、无有效档位或配置无效。
- `price_status=missing_cache_usage`：缺少计价所需的缓存命中量。
- `complete=false`：中断或无效用量。汇总中的 token 是已知小计，`total_price=null`；已知费用保留在 `known_costs`。
- `source=not_called`：输入审核等本地预设回复，没有调用模型，token 与费用确实为零。

同一次用户提问中的每轮 LLM 调用都计入总量，包括产生工具参数的轮次；纯工具执行不增加 LLM token。本轮再次发送的历史消息仍是本轮输入。标题、摘要、建议问题、独立 Workflow 暂不包含在统计范围内。历史记录不会回填估算值。

## 离线验证

在 `llmops-api/` 执行：

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest \
  test/internal/core/language_model/test_usage.py \
  test/internal/core/language_model/test_usage_migration.py \
  test/internal/core/agent/test_usage.py \
  test/internal/service/test_agent_usage_persistence.py
```

SDK 流式路径通过 HTTP MockTransport 验证，无付费请求。持久化测试验证 ORM 保存值、重复保存和历史序列化；迁移测试只生成 PostgreSQL DDL，不连接数据库。这些测试不代替真实开发数据库迁移和供应商账单核对。
