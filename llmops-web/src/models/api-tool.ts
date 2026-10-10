import { type BasePaginatorResponse, type BaseResponse } from '@/models/base'

export type ApiToolHeader = { key: string; value: string }
export type ApiToolInput = {
  type: string
  name: string
  required: boolean
  description: string
}

// 列表和提供者详情均返回原始 Schema，不返回 tools/description。
export type ApiToolProvider = {
  id: string
  name: string
  icon: string
  openapi_schema: string
  headers: ApiToolHeader[]
  created_at: number
}
export type GetApiToolProvidersWithPageResponse = BasePaginatorResponse<ApiToolProvider>

export type ApiToolSummary = {
  name: string
  description: string
  method: 'get' | 'post'
  path: string
  inputs: ApiToolInput[]
}
export type ApiToolProviderView = ApiToolProvider & {
  description: string
  tools: ApiToolSummary[]
  schemaError: string
}

// 新增自定义API插件提供者请求结构
export type CreateApiToolProviderRequest = {
  name: string
  icon: string
  openapi_schema: string
  headers: ApiToolHeader[]
}

// 更新自定义API工具提供者请求与响应结构
export type UpdateApiToolProviderRequest = CreateApiToolProviderRequest

// 获取自定义API工具提供者响应结构体
export type GetApiToolProviderResponse = BaseResponse<ApiToolProvider>

// 获取自定义API工具详情
export type GetApiToolResponse = BaseResponse<{
  id: string
  name: string
  description: string
  provider: {
    id: string
    name: string
    icon: string
    headers: { key: string; value: string }[]
    description: string
  }
  inputs: ApiToolInput[]
}>
