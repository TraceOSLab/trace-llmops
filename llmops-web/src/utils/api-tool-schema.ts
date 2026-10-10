import type { ApiToolProvider, ApiToolProviderView, ApiToolSummary } from '@/models/api-tool'

const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)

/** 提取项目 Schema 的展示信息；保存时仍由后端执行完整校验。 */
export function parseApiToolSchema(source: string) {
  const tools: ApiToolSummary[] = []
  try {
    const schema: unknown = JSON.parse(source)
    if (!isObject(schema) || !isObject(schema.paths)) throw new Error('invalid schema')
    for (const [path, item] of Object.entries(schema.paths)) {
      if (!isObject(item)) continue
      for (const method of ['get', 'post'] as const) {
        const operation = item[method]
        if (
          !isObject(operation) ||
          typeof operation.operationId !== 'string' ||
          !operation.operationId.trim() ||
          typeof operation.description !== 'string'
        )
          continue
        tools.push({
          name: operation.operationId,
          description: operation.description,
          method,
          path,
          inputs: (Array.isArray(operation.parameters) ? operation.parameters : [])
            .filter((parameter) => isObject(parameter) && typeof parameter.name === 'string')
            .map((parameter) => ({
              name: parameter.name,
              type: typeof parameter.type === 'string' ? parameter.type : '',
              description: typeof parameter.description === 'string' ? parameter.description : '',
              required: parameter.required === true,
            })),
        })
      }
    }
    return {
      description: typeof schema.description === 'string' ? schema.description : '',
      tools,
      schemaError: '',
    }
  } catch {
    return { description: '', tools: [], schemaError: 'Schema 无法解析，请编辑工具检查配置。' }
  }
}

export function toApiToolProviderView(provider: ApiToolProvider): ApiToolProviderView {
  return { ...provider, ...parseApiToolSchema(provider.openapi_schema) }
}
