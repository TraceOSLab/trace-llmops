# 自定义工具页与接口数据

工具管理页 `/space/tools` 与创建入口 `/space/tools?create=1` 共用同一列表。创建入口额外打开表单。

## 响应与展示

`GET /api-tools` 返回分页数据。列表项和 `GET /api-tools/{provider_id}` 详情均包含 `id`、`name`、`icon`、`openapi_schema`、`headers`、`created_at`，没有 `tools` 或 `description` 字段。

前端在 `src/utils/api-tool-schema.ts` 中解析原始 Schema：顶层 `description` 用于提供者描述，`paths` 下的 `get/post` 用于工具数量与名称，操作的 `parameters` 用于详情参数。省略 `parameters` 表示没有输入参数。解析失败的历史数据仍能打开编辑页，并提示检查配置。

`src/hooks/use-tool.ts` 统一把列表响应转换为展示数据，供工具管理页、应用关联插件和工作流插件节点使用。工具参数详情接口仍为 `GET /api-tools/{provider_id}/tools/{tool_name}`；应用工具设置和工作流节点使用该接口的 `inputs`。

## 创建与编辑

后端当前接受项目定义的 JSON Schema 格式，并非完整的标准 OpenAPI 文档。最小示例：

```json
{
  "server": "https://example.test",
  "description": "业务查询服务",
  "paths": {
    "/search": {
      "get": {
        "operationId": "search",
        "description": "搜索资料",
        "parameters": [
          {
            "name": "q",
            "in": "query",
            "type": "str",
            "description": "搜索关键词",
            "required": true
          }
        ]
      }
    }
  }
}
```

仅支持 `get/post`；参数类型为 `str/int/float/bool`，位置为 `path/query/header/cookie/request_body`。路径占位符必须与必填路径参数一致。最终校验由后端 `OpenAPISchema` 完成，前端的工具预览不代表校验通过。

创建调用 `POST /api-tools`，更新调用 `POST /api-tools/{provider_id}`。仅提交 `name`、`icon`、`openapi_schema`、`headers`，不包含上传列表等 UI 状态。名称最多 30 字，图标必须上传成功；Headers 的 key 不得为空，key/value 不得包含换行。Schema 在失焦及提交时通过 `POST /api-tools/validate-openapi-schema` 校验。

保存失败保留表单，成功才关闭并等待列表刷新。取消、重新创建均重置图标和 Headers。创建弹窗关闭后移除 `create=1`，避免刷新再次打开。

删除调用 `POST /api-tools/{provider_id}/delete`，仅成功才关闭表单和刷新；失败允许重试。应用移除一个关联工具时，以提供者 ID 与工具名共同匹配，保留同提供者的其他工具。

## 搜索、分页与验证

搜索通过 `search_word` 请求后端。列表刷新关闭旧详情，详情和编辑目标使用提供者 ID，避免索引错位。新搜索发起后忽略旧请求响应；加载中不重复请求下一页，最后一页与空列表停止分页。列表加载失败展示错误与重试入口。

`tests/api-tools.test.ts` 验证真实响应结构的转换、损坏 Schema、可选参数、分页和搜索竞态；`tests/e2e/tools.spec.ts` 验证两个入口、编辑、失败保留、表单清理、删除、搜索、应用插件和工作流插件。夹具直接返回原始 Schema，不补造 `tools/description` 字段。

浏览器测试固定 API 地址为本地 Mock，并拦截外部网络。这些测试不代表真实账号、数据库或第三方工具调用已联调通过。
