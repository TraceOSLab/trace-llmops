# 功能对照表

保留 demo 的业务能力，以当前后端路由与 Schema 为最终契约。以下均为真实 API 接入代码，Mock 只用于测试。

| 原功能 | 新入口与交互 | API 范围 | 验收重点 |
| --- | --- | --- | --- |
| 密码 / GitHub 登录 | 品牌登录页，回到登录前地址 | `/auth/*`, `/oauth/*` | 密码登录、失效跳转；GitHub 需真实配置另验 |
| 账号设置、退出 | 侧栏账号入口 | `/account/*`, `/upload-files/image` | 昵称、头像、密码与退出 |
| 首页助手 | `/assistant` 独立聊天页 | `/assistant-agent/*`, `/ai/suggested-questions` | 流式回复、历史、清空、停止、建议问题 |
| 原个人空间 | 一级应用、工作流、知识库、工具导航 | 各资源列表接口 | 搜索、加载、空状态与创建入口 |
| 应用增删改复制 | `/space/apps` | `/apps`, `/apps/:id`, `/copy`, `/delete` | 创建、编辑、复制、删除及刷新 |
| 应用配置 | 双栏编排、模型/任务/能力分区 | `/draft-app-config`, `/language-models/*` | 原模型选择、参数、轮数、提示词与能力持久化 |
| AI 提示词优化 | 任务配置内优化入口 | `/ai/optimize-prompt` | 流式优化、显式替换原提示词 |
| 工具、知识库、工作流关联 | 应用能力区 | 内置工具、自定义工具、知识库、已发布工作流列表 | 关联与移除不替换用户其他配置 |
| 开场白、建议问题、记忆、审查 | 应用能力区 | `/draft-app-config`, `/summary` | 配置与长期记忆查看修改 |
| 应用调试聊天 | 编排右栏 | `/apps/:id/conversations*` | 先保存后生成、错误/停止/超时、历史、清空与用量 |
| 发布、取消与历史回退 | 应用顶部与发布页 | `/publish`, `/cancel-publish`, `/publish-histories`, `/fallback-history` | 草稿与线上配置分离、回退刷新 |
| 原发布占位页 | 分享链接及 API 接入卡片 | `/published-config`, `/regenerate-web-app-token` | 未发布状态、复制/打开/重置链接 |
| 独立 WebApp（新增） | `/web-apps/:token` | `/web-apps/*`, `/conversations/*` | 登录返回、会话列表、重命名、置顶、删除与聊天 |
| 应用统计 | 应用「分析」 | `/analysis/:id` | 现有七日指标与趋势；注明历史费用统计边界 |
| 工作流管理 | `/space/workflows` | `/workflows*` | 创建、更新、搜索、删除、状态筛选 |
| 八类工作流节点 | 节点库 + 画布 + 属性面板 | `/draft-graph` | 开始、LLM、工具、代码、检索、HTTP、模板、结束 |
| 图与变量编排 | 画布内连接、删除、缩放、布局与变量引用 | 完整 `nodes` / `edges` | 位置和模型保留、序列化、草稿重载 |
| 工作流调试与发布 | 顶部操作 + 底部运行面板 | `/debug`, `/publish`, `/cancel-publish` | 节点输入输出和错误，必须出现成功结束节点 |
| 知识库 CRUD | `/space/datasets` | `/datasets*` | 创建、编辑、删除与查询 |
| 文档上传、分段、索引 | 知识库文档页三级步骤 | `/upload-files/file`, `/documents`, `/documents/batch/:batch` | 上传成功后再创建；失败/暂停刷新不重复创建 |
| 文档与分段 CRUD | 文档表格、分段卡片 | `/documents/*`, `/segments/*` | 重命名、启停、删除，分段新增编辑关键词 |
| 检索测试与记录 | 知识库文档页 | `/hit`, `/queries` | 策略/阈值/数量、命中内容与历史查询 |
| 自定义工具 | `/space/tools` | `/api-tools*`, `/validate-openapi-schema` | 图标、Schema、请求头、校验、增删改 |
| 应用模板 / 内置工具 | 资源中心两入口 | `/builtin-apps*`, `/builtin-tools*` | 分类、详情、模板加入空间，保留真实资源来源 |
| API 文档与密钥 | `/openapi`, `/openapi/api-keys` | `/openapi/api-keys*` | 接入示例、复制、遮挡、创建编辑启停删除 |

范围不包含新增注册/密码找回邮件、匿名访问、团队权限、模型密钥配置、移动端图编辑及后端契约变更。登录页沿用“忘记密码请联系管理员”的现有能力边界。
