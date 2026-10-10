// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { parseApiToolSchema, toApiToolProviderView } from '../src/utils/api-tool-schema'
import { useGetApiToolProvidersWithPage } from '../src/hooks/use-tool'
import { getApiToolProvidersWithPage } from '../src/services/api-tool'
vi.mock('../src/services/api-tool', () => ({
  getApiToolProvidersWithPage: vi.fn(),
  getApiTool: vi.fn(),
}))
const provider = {
  id: 'provider-1',
  name: '测试服务',
  icon: '',
  headers: [],
  created_at: 0,
  openapi_schema: JSON.stringify({
    server: 'https://example.test',
    description: '服务说明',
    paths: {
      '/search': {
        get: {
          operationId: 'search',
          description: '搜索',
          parameters: [
            { name: 'q', in: 'query', type: 'str', description: '关键词', required: true },
          ],
        },
      },
      '/ping': {
        post: { operationId: 'ping', description: '健康检查' },
        delete: { operationId: 'ignored', description: '' },
      },
    },
  }),
}
const response = (items = [provider], current_page = 1, total_page = 1) => ({
  code: 'success',
  message: '',
  data: {
    list: items,
    paginator: { current_page, total_page, page_size: 20, total_record: items.length },
  },
})
const request = vi.mocked(getApiToolProvidersWithPage)
const wrappers: ReturnType<typeof mount>[] = []
function setup() {
  let state!: ReturnType<typeof useGetApiToolProvidersWithPage>
  wrappers.push(
    mount(
      defineComponent({
        setup() {
          state = useGetApiToolProvidersWithPage()
          return () => null
        },
      }),
    ),
  )
  return state
}
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.resetAllMocks()
})
it('derives tools and optional parameters from the raw backend record', () => {
  const view = toApiToolProviderView(provider)
  expect(view.description).toBe('服务说明')
  expect(view.tools.map((tool) => tool.name)).toEqual(['search', 'ping'])
  expect(view.tools[0].inputs).toEqual([
    { name: 'q', type: 'str', description: '关键词', required: true },
  ])
  expect(view.tools[1].inputs).toEqual([])
  expect(view.schemaError).toBe('')
})
it.each(['', '{', 'null', '[]', '{"paths":null}'])(
  'handles malformed stored schema %s',
  (source) => {
    expect(parseApiToolSchema(source).tools).toEqual([])
    expect(parseApiToolSchema(source).schemaError).not.toBe('')
  },
)
it('handles incomplete drafts safely', () => {
  const parsed = parseApiToolSchema(
    JSON.stringify({
      paths: {
        '/empty': null,
        '/test': {
          get: null,
          post: { operationId: 'test', description: '', parameters: [null, {}, { name: 'q' }] },
        },
      },
    }),
  )
  expect(parsed.tools[0].inputs).toEqual([
    { name: 'q', type: '', description: '', required: false },
  ])
})
it('does not repeat an empty page', async () => {
  request.mockResolvedValueOnce(response([]))
  const state = setup()
  await state.loadApiToolProviders(true)
  await state.loadApiToolProviders()
  expect(request).toHaveBeenCalledTimes(1)
  expect(state.loading.value).toBe(false)
})
it('normalizes all pages and prevents duplicate concurrent loads', async () => {
  request
    .mockResolvedValueOnce(response([provider], 1, 2))
    .mockResolvedValueOnce(response([{ ...provider, id: 'provider-2' }], 2, 2))
  const state = setup()
  await state.loadApiToolProviders(true, '测试')
  await Promise.all([
    state.loadApiToolProviders(false, '测试'),
    state.loadApiToolProviders(false, '测试'),
  ])
  await state.loadApiToolProviders(false, '测试')
  expect(request).toHaveBeenNthCalledWith(2, 2, 20, '测试')
  expect(request).toHaveBeenCalledTimes(2)
  expect(state.api_tool_providers.map((item) => item.id)).toEqual(['provider-1', 'provider-2'])
  expect(state.api_tool_providers[1].tools).toHaveLength(2)
})
it('discards an older search response', async () => {
  let resolveOld!: (value: ReturnType<typeof response>) => void
  request
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        }),
    )
    .mockResolvedValueOnce(response([{ ...provider, id: 'new' }]))
  const state = setup()
  const old = state.loadApiToolProviders(true, 'old')
  await state.loadApiToolProviders(true, 'new')
  resolveOld(response())
  await old
  expect(state.api_tool_providers.map((item) => item.id)).toEqual(['new'])
  expect(state.paginator.current_page).toBe(2)
  expect(state.loading.value).toBe(false)
})
it('exposes a load failure and allows retry', async () => {
  request.mockRejectedValueOnce(new Error('测试请求失败')).mockResolvedValueOnce(response())
  const state = setup()
  await state.loadApiToolProviders(true)
  expect(state.error.value).toBe('测试请求失败')
  expect(state.loading.value).toBe(false)
  await state.loadApiToolProviders(true)
  expect(state.error.value).toBe('')
  expect(state.api_tool_providers).toHaveLength(1)
})
