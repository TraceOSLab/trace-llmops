import { test, expect } from '@playwright/test'
import { apiProvider, appId, mock, toolSchema, workflowId } from './fixtures'
for (const path of ['/space/tools', '/space/tools?create=1']) {
  test(`raw provider renders without length errors: ${path}`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await mock(page)
    await page.goto(path)
    await expect(page.locator('.arco-card').filter({ hasText: '测试服务' })).toContainText('2 插件')
    if (path.includes('create')) {
      await expect(page.getByText('新建插件', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: '取消', exact: true }).click()
      await expect(page).toHaveURL(/\/space\/tools$/)
    }
    await expect(page.getByText('测试服务说明', { exact: true })).toBeVisible()
    await page.locator('.arco-card').filter({ hasText: '测试服务' }).click()
    const drawer = page.locator('.arco-drawer:visible')
    await expect(drawer.getByText('search', { exact: true })).toBeVisible()
    await expect(drawer.getByText('搜索关键词', { exact: true })).toBeVisible()
    await expect(drawer.getByText('ping', { exact: true })).toBeVisible()
    if (path === '/space/tools')
      await page.screenshot({
        path: 'test-results/tool-detail.png',
        fullPage: true,
        animations: 'disabled',
      })
    await expect(page.locator('.global-error')).toHaveCount(0)
    expect(errors).toEqual([])
  })
}
test('edit uses exact contract and creation does not inherit icon or headers', async ({ page }) => {
  const calls = await mock(page)
  await page.goto('/space/tools')
  await page.locator('.arco-card').filter({ hasText: '测试服务' }).click()
  await page.getByRole('button', { name: '编辑工具' }).click()
  const modal = page.locator('.arco-modal:visible')
  await expect(modal.getByPlaceholder('请输入请求头键名')).toHaveValue('X-Test')
  await expect(modal.getByText('更新插件', { exact: true })).toBeVisible()
  await expect(modal).toHaveCSS('opacity', '1')
  await page.screenshot({
    path: 'test-results/tool-editor.png',
    fullPage: true,
    animations: 'disabled',
  })
  await modal.getByPlaceholder('请输入插件名称，确保名称含义清晰').fill('修改后的服务')
  await modal.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('修改后的服务', { exact: true })).toBeVisible()
  expect(
    calls.find((call) => call.path === `/api-tools/${apiProvider.id}` && call.body)?.body,
  ).toEqual({
    name: '修改后的服务',
    icon: apiProvider.icon,
    openapi_schema: apiProvider.openapi_schema,
    headers: apiProvider.headers,
  })
  await page.getByRole('button', { name: '创建工具', exact: true }).click()
  await expect(modal.getByPlaceholder('请输入插件名称，确保名称含义清晰')).toHaveValue('')
  await expect(modal.getByPlaceholder('请输入请求头键名')).toHaveCount(0)
  await modal.getByPlaceholder('请输入插件名称，确保名称含义清晰').fill('缺图标服务')
  await modal.getByPlaceholder('在此处输入您的 OpenAPI Schema').fill(JSON.stringify(toolSchema))
  await modal.getByRole('button', { name: '保存', exact: true }).click()
  await expect(modal.getByText('插件图标不能为空', { exact: true })).toBeVisible()
  expect(calls.filter((call) => call.path === '/api-tools' && call.body)).toHaveLength(0)
})
test('invalid schema and failed update retain form; retry and delete succeed', async ({ page }) => {
  const calls = await mock(page)
  let failUpdate = true
  await page.route(`http://localhost:5000/api-tools/${apiProvider.id}`, async (route) => {
    if (route.request().method() === 'POST' && failUpdate)
      await route.fulfill({ json: { code: 'fail', message: '测试保存失败' } })
    else await route.fallback()
  })
  await page.goto('/space/tools')
  await page.locator('.arco-card').filter({ hasText: '测试服务' }).click()
  await page.getByRole('button', { name: '编辑工具' }).click()
  const modal = page.locator('.arco-modal:visible')
  const schema = modal.getByPlaceholder('在此处输入您的 OpenAPI Schema')
  await schema.fill('{"servers":[]}')
  await modal.getByRole('button', { name: '保存', exact: true }).click()
  await expect(
    modal.getByText('Schema 必须包含 server、description、paths', { exact: true }),
  ).toBeVisible()
  expect(calls.some((call) => call.path === `/api-tools/${apiProvider.id}` && call.body)).toBe(
    false,
  )
  await schema.fill(JSON.stringify(toolSchema))
  await modal.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('测试保存失败', { exact: true })).toBeVisible()
  await expect(schema).toHaveValue(JSON.stringify(toolSchema))
  failUpdate = false
  await modal.getByRole('button', { name: '保存', exact: true }).click()
  await expect(modal).toHaveCount(0)
  await page.locator('.arco-card').filter({ hasText: '测试服务' }).click()
  await page.getByRole('button', { name: '编辑工具' }).click()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await page
    .locator('.arco-modal:visible')
    .filter({ hasText: '删除这个工具?' })
    .getByRole('button', { name: '确定', exact: true })
    .click()
  await expect(page.getByText('没有可用的API插件', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('没有可用的API插件', { exact: true })).toBeVisible()
})
test('search closes stale details and renders empty results', async ({ page }) => {
  await mock(page)
  await page.goto('/space/tools')
  await page.locator('.arco-card').filter({ hasText: '测试服务' }).click()
  await page.goto('/space/tools?search_word=不存在')
  await expect(page.getByText('没有可用的API插件', { exact: true })).toBeVisible()
  await expect(page.locator('.arco-drawer:visible')).toHaveCount(0)
  await expect(page.locator('.global-error')).toHaveCount(0)
})
test('app picker uses schema tools and API detail inputs', async ({ page }) => {
  const calls = await mock(page)
  await page.goto(`/space/apps/${appId}`)
  const section = page.locator('.arco-collapse-item').filter({ hasText: '扩展插件' })
  await section.getByRole('button', { name: '关联插件', exact: true }).click()
  const modal = page.locator('.arco-modal:visible')
  await expect(modal.getByText('search', { exact: true })).toBeVisible()
  const row = modal.locator('div.group').filter({ hasText: 'search' })
  await row.hover()
  await row.getByRole('button', { name: '添加', exact: true }).click()
  await expect
    .poll(() =>
      calls.some(
        (call) =>
          call.path.endsWith('/draft-app-config') && call.body?.tools?.[0]?.tool_id === 'search',
      ),
    )
    .toBe(true)
  await modal.getByRole('button', { name: '关闭插件选择', exact: true }).click()
  await expect(modal).toHaveCount(0)
  const selected = section.locator('div.group').filter({ hasText: '测试服务 / search' })
  await selected.hover()
  await selected.getByRole('button', { name: '工具设置', exact: true }).click()
  await expect(
    page.locator('.arco-modal:visible').getByText('搜索关键词', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.global-error')).toHaveCount(0)
})

test('removing one API tool keeps another tool from the same provider', async ({ page }) => {
  const calls = await mock(page)
  await page.goto(`/space/apps/${appId}`)
  await page.getByRole('button', { name: '关联插件', exact: true }).click()
  const modal = page.locator('.arco-modal:visible')
  const search = modal.locator('div.group').filter({ hasText: 'search' })
  const ping = modal.locator('div.group').filter({ hasText: 'ping' })
  await search.hover()
  await search.getByRole('button', { name: '添加', exact: true }).click()
  await expect(search.getByRole('button', { name: '删除', exact: true })).toBeVisible()
  await ping.hover()
  await ping.getByRole('button', { name: '添加', exact: true }).click()
  await expect(ping.getByRole('button', { name: '删除', exact: true })).toBeVisible()
  await search.hover()
  await search.getByRole('button', { name: '删除', exact: true }).click()
  await expect(search.getByRole('button', { name: '添加', exact: true })).toBeVisible()
  const saves = calls.filter((call) => call.path.endsWith('/draft-app-config') && call.body?.tools)
  expect(saves.at(-1)?.body.tools.map((item: any) => item.tool_id)).toEqual(['ping'])
})

test('workflow picker binds API tool and loads its input parameters', async ({ page }) => {
  const calls = await mock(page)
  await page.goto(`/space/workflows/${workflowId}`)
  await page
    .locator('.node-library')
    .getByRole('button', { name: /扩展插件/ })
    .click()
  await page.getByRole('button', { name: '绑定插件', exact: true }).click()
  const modal = page.locator('.arco-modal:visible')
  const row = modal.locator('div.group').filter({ hasText: 'search' })
  await row.hover()
  await row.getByRole('button', { name: '添加', exact: true }).click()
  await expect
    .poll(() => calls.some((call) => call.path === `/api-tools/${apiProvider.id}/tools/search`))
    .toBe(true)
  await modal.getByRole('button', { name: '关闭插件选择', exact: true }).click()
  await expect(page.getByText('q', { exact: true })).toBeVisible()
  await expect(page.locator('.global-error')).toHaveCount(0)
})
