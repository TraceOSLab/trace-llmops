import type { Page } from '@playwright/test'
export const appId = '11111111-1111-4111-8111-111111111111',
  workflowId = '22222222-2222-4222-8222-222222222222'
export const app = {
  id: appId,
  name: '产品知识助手',
  icon: '',
  description: '连接产品知识，给出可靠回答',
  status: 'published',
  model_config: { provider: 'local', model: 'test' },
  created_at: 1780000000,
  updated_at: 1780000000,
  draft_updated_at: 1780000000,
}
export const workflow = {
  id: workflowId,
  name: '内容处理流程',
  icon: '',
  description: '从输入到输出',
  status: 'draft',
  node_count: 2,
  is_debug_passed: true,
  updated_at: 1780000000,
  created_at: 1780000000,
}
export const draft = {
  model_config: { provider: 'local', model: 'test', parameters: {} },
  dialog_round: 3,
  preset_prompt: '你是一位专业的产品助手。',
  tools: [],
  workflows: [],
  datasets: [],
  retrieval_config: { retrieval_strategy: 'semantic', k: 4, score: 0 },
  long_term_memory: { enable: false },
  opening_statement: '你好，可以向我询问产品知识。',
  opening_questions: ['介绍产品'],
  suggested_after_answer: { enable: false },
  review_config: {
    enable: false,
    keywords: [],
    inputs_config: { enable: false, preset_response: '' },
    outputs_config: { enable: false },
  },
}
export async function mock(page: Page, login = true) {
  let datasets: any[] = [
    {
      id: 'dataset-1',
      name: '产品知识库',
      icon: '',
      description: '产品说明与帮助文档',
      document_count: 1,
      character_count: 100,
      hit_count: 0,
      related_app_count: 0,
      created_at: 1780000000,
      updated_at: 1780000000,
    },
  ]
  let document = {
    id: 'document-1',
    dataset_id: 'dataset-1',
    name: '产品说明.txt',
    segment_count: 1,
    character_count: 100,
    hit_count: 0,
    position: 1,
    enabled: true,
    status: 'completed',
    error: '',
    created_at: 1780000000,
    updated_at: 1780000000,
  }
  let segments: any[] = [
    {
      id: 'segment-1',
      dataset_id: 'dataset-1',
      document_id: 'document-1',
      position: 1,
      content: '这是产品说明片段',
      keywords: ['产品'],
      character_count: 10,
      token_count: 10,
      hit_count: 0,
      enabled: true,
      status: 'completed',
      created_at: 1780000000,
      updated_at: 1780000000,
    },
  ]
  let providers: any[] = []
  let conversations: any[] = []
  let apiKeys: any[] = [
    {
      id: appId,
      api_key: 'test-secret-do-not-show',
      is_active: true,
      remark: '本地测试',
      created_at: 1780000000,
    },
  ]
  const calls: { path: string; body: any }[] = []
  let appState = { ...app },
    draftState = structuredClone(draft),
    graph = {
      nodes: [
        {
          id: '33333333-3333-4333-8333-333333333333',
          node_type: 'start',
          title: '开始',
          description: '输入',
          position: { x: 100, y: 200 },
          inputs: [],
        },
        {
          id: '44444444-4444-4444-8444-444444444444',
          node_type: 'end',
          title: '结束',
          description: '输出',
          position: { x: 550, y: 200 },
          outputs: [],
        },
      ],
      edges: [] as any[],
    }
  if (login)
    await page.addInitScript(() =>
      localStorage.setItem(
        'credential',
        JSON.stringify({ access_token: 'test-local-only', expire_at: 9999999999 }),
      ),
    )
  await page.route('**/*', async (route) => {
    const req = route.request(),
      url = new URL(req.url())
    if (url.origin === 'http://127.0.0.1:5179') return route.continue()
    if (url.hostname !== 'localhost' || url.port !== '5000') return route.abort()
    const path = url.pathname,
      body = req.headers()['content-type']?.includes('application/json') ? req.postDataJSON() : null
    calls.push({ path, body })
    const paged = (list: any[]) => ({
      list,
      paginator: {
        current_page: 1,
        page_size: 20,
        total_page: list.length ? 1 : 0,
        total_record: list.length,
      },
    })
    let data: any = {},
      code = 'success',
      message = '操作成功'
    if (path === '/upload-files/image') data = { image_url: 'http://127.0.0.1:5179/favicon.svg' }
    else if (path === '/upload-files/file') data = { id: 'file-1', name: 'test.txt' }
    else if (path === '/datasets') {
      if (req.method() === 'POST') {
        datasets.push({ ...datasets[0], ...body, id: 'dataset-new' })
        data = { id: 'dataset-new' }
      } else
        data = paged(
          datasets.filter(
            (d) =>
              !url.searchParams.get('search_word') ||
              d.name.includes(url.searchParams.get('search_word')),
          ),
        )
    } else if (path === '/datasets/dataset-1/documents/batch/batch-1')
      data = [
        {
          ...document,
          status: 'error',
          segment_count: 0,
          completed_segment_count: 0,
          size: 100,
          error: '无法解析测试文件',
        },
      ]
    else if (path === '/datasets/dataset-1/documents')
      data =
        req.method() === 'POST' ? { batch: 'batch-1', documents: [document] } : paged([document])
    else if (path === '/datasets/dataset-1/documents/document-1/segments') {
      if (req.method() === 'POST') {
        segments.push({ ...segments[0], ...body, id: 'segment-new', position: 2 })
        data = { id: 'segment-new' }
      } else data = paged(segments)
    } else if (path === '/datasets/dataset-1/documents/document-1') data = document
    else if (path.startsWith('/datasets/dataset-1/documents/document-1/segments/')) {
      const id = path.split('/')[6],
        item = segments.find((s) => s.id === id)
      if (path.endsWith('/delete')) segments = segments.filter((s) => s.id !== id)
      else if (req.method() === 'POST') Object.assign(item, body)
      else data = item
    } else if (path === '/datasets/dataset-1/documents/document-1/enabled')
      document.enabled = body.enabled
    else if (path === '/datasets/dataset-1/queries') data = []
    else if (path === '/datasets/dataset-1/hit') data = []
    else if (path.startsWith('/datasets/')) {
      const id = path.split('/')[2]
      if (path.endsWith('/delete')) datasets = datasets.filter((d) => d.id !== id)
      else if (req.method() === 'POST') Object.assign(datasets.find((d) => d.id === id) || {}, body)
      else data = datasets.find((d) => d.id === id)
    } else if (path === '/api-tools/validate-openapi-schema') data = {}
    else if (path === '/api-tools') {
      if (req.method() === 'POST') {
        providers.push({
          id: 'provider-1',
          ...body,
          description: '测试工具',
          tools: [],
          created_at: 1780000000,
        })
        data = { id: 'provider-1' }
      } else data = paged(providers)
    } else if (path === '/auth/password-login')
      data = { access_token: 'test-local-only', expire_at: 9999999999 }
    else if (path === '/account')
      data = { id: appId, name: 'Youyou', email: 'youyou@example.test', avatar: '' }
    else if (path === '/apps') data = req.method() === 'POST' ? { id: appId } : paged([appState])
    else if (path === `/apps/${appId}`) data = appState
    else if (path.endsWith('/draft-app-config')) {
      if (req.method() === 'POST') draftState = { ...draftState, ...body }
      data = draftState
    } else if (path.endsWith('/publish')) appState.status = 'published'
    else if (path.endsWith('/cancel-publish')) appState.status = 'draft'
    else if (path.endsWith('/published-config'))
      data = { web_app: { token: 'local-test', status: appState.status } }
    else if (path.endsWith('/publish-histories'))
      data = paged([{ id: workflowId, version: 1, created_at: 1780000000 }])
    else if (path === '/workflows')
      data = req.method() === 'POST' ? { id: workflowId } : paged([workflow])
    else if (path === `/workflows/${workflowId}`) data = workflow
    else if (path.endsWith('/draft-graph')) {
      if (req.method() === 'POST') graph = body
      data = graph
    } else if (path === '/language-models')
      data = [
        {
          name: 'local',
          label: '本地测试',
          icon: '',
          models: [{ model_name: 'test', label: 'Test Model' }],
        },
      ]
    else if (path === '/language-models/local/test')
      data = {
        model_name: 'test',
        label: 'Test Model',
        parameters: [],
        features: [],
        metadata: { context_size: 1000 },
      }
    else if (path.endsWith('/icon'))
      return route.fulfill({
        status: 200,
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg"/>',
      })
    else if (path === '/web-apps/local-test') data = { ...app, app_config: draftState }
    else if (
      path.endsWith('/conversations') &&
      req.method() === 'GET' &&
      path.startsWith('/web-apps')
    )
      data = conversations.filter(
        (c) => c.is_pinned === (new URL(req.url()).searchParams.get('is_pinned') === 'true'),
      )
    else if (path.startsWith('/conversations/')) {
      const id = path.split('/')[2]
      if (path.endsWith('/delete')) conversations = conversations.filter((c) => c.id !== id)
      else if (req.method() === 'POST')
        Object.assign(conversations.find((c) => c.id === id) || {}, body)
      else data = paged([])
    } else if (path.endsWith('/messages') || path === '/assistant-agent/messages') data = paged([])
    else if (path.endsWith('/summary')) data = { summary: '' }
    else if (path.includes('/analysis/')) {
      data = Object.fromEntries(
        [
          'total_messages',
          'active_accounts',
          'avg_of_conversation_messages',
          'token_output_rate',
          'cost_consumption',
        ].map((k) => [k, { data: 0, pop: 0 }]),
      )
      for (const k of [
        'total_messages_trend',
        'active_accounts_trend',
        'avg_of_conversation_messages_trend',
        'cost_consumption_trend',
      ])
        data[k] = { x_axis: [], y_axis: [] }
    } else if (path.endsWith('/chat') || path === `/apps/${appId}/conversations`) {
      const id = '55555555-5555-4555-8555-555555555555'
      if (path.startsWith('/web-apps') && !conversations.some((c) => c.id === id))
        conversations.push({ id, name: '新测试会话', is_pinned: false })
      return route.fulfill({
        contentType: 'text/event-stream',
        body: `event: agent_message\ndata: ${JSON.stringify({ id, answer: '这是本地模拟的回答。', message_id: id, task_id: id, conversation_id: id })}\n\nevent: agent_end\ndata: {"usage":{"complete":false,"total_price":null}}\n\n`,
      })
    } else if (path.endsWith('/debug'))
      return route.fulfill({
        contentType: 'text/event-stream',
        body: 'event: workflow\ndata: {"id":"end","node_data":{"node_type":"end","title":"结束"},"status":"succeeded","outputs":{"result":"完成"},"inputs":{},"latency":0.01}\n\n',
      })
    else if (path === '/openapi/api-keys') {
      if (req.method() === 'POST')
        apiKeys.push({ id: 'new-key', api_key: 'new-test-secret', created_at: 1780000000, ...body })
      data = paged(apiKeys)
    } else if (path.startsWith('/openapi/api-keys/')) {
      const id = path.split('/')[3]
      if (path.endsWith('/delete')) apiKeys = apiKeys.filter((k) => k.id !== id)
      else Object.assign(apiKeys.find((k) => k.id === id) || {}, body)
    } else if (path.includes('/builtin-')) data = []
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code, message, data }),
    })
  })
  return calls
}
