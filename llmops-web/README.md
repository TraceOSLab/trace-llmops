# Trace LLMOPS · Web

Youyou 的 AI 应用工作台。Vue 3 + TypeScript + Vite，浅色青绿主题，覆盖应用、工作流、知识库、工具、资源中心、开放 API、助手与已发布应用聊天。

## 启动

在仓库根目录运行：

```sh
pnpm install --frozen-lockfile
pnpm dev:web
```

打开终端显示的本地地址（默认 `http://127.0.0.1:5173`）。需要现有 Flask 后端提供登录和业务 API；后端启动遵循仓库 `docs/runbooks/development.md`。

前端默认连接 `http://localhost:5000`，可通过环境变量指定：

```sh
VITE_API_BASE_URL=http://localhost:5000 pnpm dev:web
```

配置项见 `.env.example`。Vite 在构建时注入 API 地址；不要把 API 密钥或模型凭证放入 `VITE_*`。浏览器直连后端，后端须允许实际前端 origin 与认证请求头。没有修改现有后端 CORS 或鉴权配置。

## 检查与构建

```sh
pnpm --filter trace-llmops-web type-check
pnpm --filter trace-llmops-web lint
pnpm --filter trace-llmops-web test
pnpm --filter trace-llmops-web build
pnpm --filter trace-llmops-web preview
```

浏览器测试使用本地构建和模拟 API，不需要登录真实账号，不调用真实后端、付费模型或外部工具：

```sh
# 已安装 Google Chrome 时
PLAYWRIGHT_CHANNEL=chrome pnpm --filter trace-llmops-web test:e2e

# 或一次性安装 Playwright Chromium，之后执行测试
pnpm --filter trace-llmops-web exec playwright install chromium
pnpm --filter trace-llmops-web test:e2e
```

测试自身拦截所有非前端请求，API 请求由内存数据响应，其他域名直接阻断。浏览器启动需允许创建隔离用户目录。测试端口为 5179；截图与失败追踪保存在 `test-results/`，不提交。

## 使用约定

- 应用提示词自动保存，并在调试、发布、历史回退前等待保存完成；失败提示支持重试。
- 工作流节点表单先点击“保存”应用到画布，再点击顶部“保存草稿”；调试前自动保存整个图。未保存时离开有提示。仅调试通过且无后续修改的工作流可发布。
- 修改草稿不会自动替换已发布配置，需显式更新发布。
- WebApp 分享链接为 `/web-apps/:token`，当前后端要求访问者登录；未登录会先跳转登录再回到分享页面。
- 模型报错、超时、停止、断流都会结束生成状态并保留已收到的内容。不自动重发模型请求，不提供事件重放。
- 用量遵循后端 `usage`，未知费用与不完整统计明确标注；费用“按价目表计算”，不是供应商账单。
- 手机支持列表、基本管理、登录和聊天。工作流图编辑需要桌面浏览器。

## 代码组织

- `src/views`：工作台布局与各业务页面。路由保留课程既有地址，新增 `/assistant` 与 `/web-apps/:token`。
- `src/components`：共享聊天与保存状态；`assets/styles/main.css` 定义全局视觉规范。
- `src/services` / `models`：HTTP 请求和已有后端结构；`hooks` 组织业务状态。
- `src/utils/request.ts` / `sse.ts` / `chat.ts`：请求、分片解析、聊天步骤及用量合并。
- `src/utils/draft-queue.ts`：按应用隔离的串行保存与防抖；`workflow-graph.ts`：后端图与 Vue Flow 图转换。

课程 demo 原样保留在相邻目录。业务表单、资源操作和节点配置从课程功能迁移；工作台、导航、登录展示、编排布局、画布容器、发布页、共享聊天及请求/流处理重新实现。详情见 [功能对照表](docs/feature-matrix.md) 与 [实现说明](docs/implementation.md)、[验证记录](docs/verification.md)。

部署输出为 `dist/`；静态服务器应把前端历史路由回退到 `index.html`。本次不部署站点、不修改基础设施。
