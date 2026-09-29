import { test, expect } from '@playwright/test'
import { mock, appId, workflowId } from './fixtures'
const image = {
  name: 'icon.png',
  mimeType: 'image/png',
  buffer: Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==',
    'base64',
  ),
}
async function uploadIcon(page: any) {
  await Promise.all([
    page.waitForResponse((r: any) => r.url().endsWith('/upload-files/image') && r.status() === 200),
    page.locator('.arco-modal:visible input[type=file]').setInputFiles(image),
  ])
}
for (const path of [
  '/space/datasets',
  '/space/tools',
  '/store/apps',
  '/store/tools',
  '/openapi',
  `/space/apps/${appId}/analysis`,
  '/space/datasets/dataset-1/documents',
  '/space/datasets/dataset-1/documents/document-1/segments',
]) {
  test(`resource route ${path} renders without errors`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await mock(page)
    await page.goto(path)
    await expect(page.locator('.workspace-main, .app-layout').first()).toBeVisible()
    await expect(page.locator('.arco-spin-loading')).toHaveCount(0)
    await expect(page.locator('.global-error')).toHaveCount(0)
    expect(errors).toEqual([])
  })
}
test('create app via dashboard shortcut and upload', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/home')
  await page.getByRole('link', { name: /创建 AI 应用/ }).click()
  await expect(page.getByPlaceholder('请输入应用名称')).toBeVisible()
  await uploadIcon(page)
  await page.getByPlaceholder('请输入应用名称').fill('新应用')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/space/apps/${appId}$`))
  expect(calls.some((c) => c.path === '/apps' && c.body?.name === '新应用')).toBe(true)
})
test('create dataset, search, and retain persisted list after reload', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/space/datasets?create=1')
  await expect(page.getByPlaceholder('请输入知识库名称')).toBeVisible()
  await uploadIcon(page)
  await page.getByPlaceholder('请输入知识库名称').fill('新知识库')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('新知识库', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('新知识库', { exact: true })).toBeVisible()
  expect(calls.some((c) => c.path === '/datasets' && c.body?.name === '新知识库')).toBe(true)
})
test('add a document segment and observe persisted content', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/space/datasets/dataset-1/documents/document-1/segments')
  await page.getByRole('button', { name: /添加片段/ }).click()
  await page.getByPlaceholder('在这里添加文档片段内容').fill('新增测试片段')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('新增测试片段', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('新增测试片段', { exact: true })).toBeVisible()
  expect(
    calls.some((c) => c.path.endsWith('/segments') && c.body?.content === '新增测试片段'),
  ).toBe(true)
})
test('upload indexing failure appears even with zero segments', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/space/datasets/dataset-1/documents/create')
  await page.locator('input[type=file][multiple]').setInputFiles({
    name: 'test.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('test content'),
  })
  await expect(page.getByText('test.txt', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('处理出错：无法解析测试文件')).toBeVisible()
  expect(calls.filter((c) => c.path === '/datasets/dataset-1/documents' && c.body).length).toBe(1)
})
test('all node settings open and workflow debug reaches end output', async ({ page }) => {
  await mock(page)
  await page.goto(`/space/workflows/${workflowId}`)
  await expect(page.getByText('内容处理流程', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '调试', exact: true }).click()
  await page.getByRole('button', { name: '开始运行' }).click()
  await expect(page.getByText('运行成功', { exact: true })).toBeVisible()
  await expect(page.getByText('500 Tokens')).toHaveCount(0)
  await page.reload()
  for (const label of [
    '大语言模型',
    '扩展插件',
    '知识库检索',
    '模板转换',
    'HTTP请求',
    'Python代码执行',
  ]) {
    await page
      .locator('.node-library')
      .getByRole('button', { name: new RegExp(label) })
      .click()
    await expect(page.locator('.node-form-actions')).toBeVisible()
    await expect(page.locator('.global-error')).toHaveCount(0)
  }
  await page.screenshot({ path: 'test-results/eight-nodes.png', fullPage: true })
})
test('stream error stops generation and preserves partial answer', async ({ page }) => {
  await mock(page)
  await page.route('**/assistant-agent/chat', (route) =>
    route.fulfill({
      contentType: 'text/event-stream',
      body: 'event: agent_message\ndata: {"id":"s","answer":"已生成部分"}\n\nevent: error\ndata: {"observation":"模型上下文过长"}\n\n',
    }),
  )
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: '输入消息' }).fill('触发错误')
  await page.getByRole('textbox', { name: '输入消息' }).press('Enter')
  await expect(page.getByText('已生成部分', { exact: true })).toBeVisible()
  await expect(page.getByText('模型上下文过长', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '输入消息' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0)
})
test('failed draft save blocks publish and retry retains input', async ({ page }) => {
  const calls = await mock(page)
  let fail = true
  await page.route('**/draft-app-config', async (route) => {
    if (fail && route.request().method() === 'POST')
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ code: 'fail', message: '保存测试失败' }),
      })
    await route.fallback()
  })
  await page.goto(`/space/apps/${appId}`)
  await page.locator('textarea').first().fill('失败也要保留')
  await page.locator('textarea').first().blur()
  await expect(page.getByText('保存失败', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '更新发布' }).click()
  expect(calls.some((c) => c.path.endsWith('/publish'))).toBe(false)
  await expect(page.locator('textarea').first()).toHaveValue('失败也要保留')
  fail = false
  await page.locator('.save-status').getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('更改已保存', { exact: true })).toBeVisible()
})
test('expired token goes to login and unavailable published app is clear', async ({ page }) => {
  await mock(page)
  await page.route('http://localhost:5000/web-apps/missing', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 'not_found', message: '应用不存在或未发布' }),
    }),
  )
  await page.goto('/web-apps/missing')
  await expect(page.getByRole('heading', { name: '无法访问此应用' })).toBeVisible()
  await page.route('http://localhost:5000/account', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'unauthorized', message: '登录已过期' }),
    }),
  )
  await page.goto('/home')
  await expect(page).toHaveURL(/auth\/login/)
})

test('create a custom OpenAPI tool and read it after reload', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/space/tools?create=1')
  await expect(page.getByPlaceholder('请输入插件名称，确保名称含义清晰')).toBeVisible()
  await uploadIcon(page)
  await page.getByPlaceholder('请输入插件名称，确保名称含义清晰').fill('本地测试工具')
  await page.getByPlaceholder('在此处输入您的 OpenAPI Schema').fill(
    JSON.stringify({
      openapi: '3.0.0',
      info: { title: 'Test', description: 'Test tool', version: '1.0' },
      servers: [{ url: 'https://example.test' }],
      paths: {
        '/ping': {
          get: {
            operationId: 'ping',
            description: '本地测试接口',
            responses: { '200': { description: 'ok' } },
          },
        },
      },
    }),
  )
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('本地测试工具', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('本地测试工具', { exact: true })).toBeVisible()
  expect(calls.some((c) => c.path === '/api-tools' && c.body?.name === '本地测试工具')).toBe(true)
})
test('restore publication history refreshes draft, and unpublish removes share link', async ({
  page,
}) => {
  const calls = await mock(page)
  await page.goto(`/space/apps/${appId}`)
  await page.getByRole('button', { name: '发布历史', exact: true }).click()
  await page.locator('.arco-drawer .arco-card').first().hover()
  await page.getByRole('button', { name: '回退', exact: true }).click()
  await expect
    .poll(() =>
      calls.some((c) => c.path.endsWith('/fallback-history') && c.body?.app_config_version_id),
    )
    .toBeTruthy()
  await page.getByRole('button', { name: '取消发布', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await page.getByRole('link', { name: '发布', exact: true }).click()
  await expect(page.getByText('应用尚未发布，点击顶部“发布应用”生成访问链接。')).toBeVisible()
})
test('mobile login and chat remain usable without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mock(page, false)
  await page.goto('/auth/login')
  await page.screenshot({ path: 'test-results/mobile-login.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByPlaceholder('登录账号').fill('youyou@example.test')
  await page.getByPlaceholder('账号密码').fill('test-only-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/home$/)
  await page.goto('/assistant')
  await page.getByRole('textbox', { name: '输入消息' }).fill('你好')
  await page.getByRole('textbox', { name: '输入消息' }).press('Enter')
  await expect(page.getByText('这是本地模拟的回答。', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/mobile-chat.png', fullPage: true })
})

test('published chat supports fresh conversation and rename, pin, delete persistence', async ({
  page,
}) => {
  const calls = await mock(page)
  await page.goto('/web-apps/local-test')
  await page.getByRole('textbox', { name: '输入消息' }).fill('第一条')
  await page.getByRole('textbox', { name: '输入消息' }).press('Enter')
  await expect(page.getByText('这是本地模拟的回答。', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '新测试会话', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新对话', exact: true }).click()
  await expect(page.getByText('这是本地模拟的回答。', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '管理会话' }).click()
  await page.getByText('重命名', { exact: true }).click()
  await page.locator('.arco-modal:visible input').first().fill('已重命名会话')
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await page.reload()
  await expect(page.getByRole('button', { name: '已重命名会话', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '管理会话' }).click()
  await page.getByText('置顶', { exact: true }).click()
  await expect(page.getByRole('button', { name: '⌃ 已重命名会话', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '管理会话' }).click()
  await page.getByText('删除', { exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await page.reload()
  await expect(page.locator('.conversation-row')).toHaveCount(0)
  expect(calls.some((c) => c.path.endsWith('/is-pinned') && c.body.is_pinned)).toBe(true)
})

test('API key creation, disable, edit and deletion persist', async ({ page }) => {
  await mock(page)
  await page.goto('/openapi/api-keys')
  await page.getByRole('button', { name: /创建.*秘钥|新增.*秘钥|创建.*密钥/ }).click()
  await page.getByPlaceholder('请输入秘钥备注，用于描述秘钥基础信息').fill('新密钥测试')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await page.reload()
  const row = page.getByRole('row').filter({ hasText: '新密钥测试' })
  await expect(row).toBeVisible()
  await row.getByRole('switch').click()
  await expect(row.getByText('可用', { exact: true })).toBeVisible()
  await row.getByRole('button', { name: '管理密钥' }).click()
  await page.getByText('重命名', { exact: true }).click()
  await page.getByPlaceholder('请输入秘钥备注，用于描述秘钥基础信息').fill('编辑后的备注')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await page.reload()
  const edited = page.getByRole('row').filter({ hasText: '编辑后的备注' })
  await edited.getByRole('button', { name: '管理密钥' }).click()
  await page.getByText('删除', { exact: true }).click()
  await page
    .locator('.arco-modal:visible')
    .getByRole('button', { name: '确定', exact: true })
    .click()
  await page.reload()
  await expect(page.getByText('编辑后的备注', { exact: true })).toHaveCount(0)
})
