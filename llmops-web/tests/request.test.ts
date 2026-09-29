import { beforeEach, afterEach, it, expect, vi } from 'vitest'
const mocked = vi.hoisted(() => ({
  clear: vi.fn(),
  replace: vi.fn().mockResolvedValue(undefined),
  error: vi.fn(),
  credential: { access_token: 'test-token' },
}))
vi.mock('@arco-design/web-vue', () => ({ Message: { error: mocked.error } }))
vi.mock('@/stores/credential', () => ({
  useCredentialStore: () => ({ credential: mocked.credential, clear: mocked.clear }),
}))
vi.mock('@/router', () => ({
  default: { currentRoute: { value: { fullPath: '/web-apps/shared' } }, replace: mocked.replace },
}))
import { get, post, ssePost } from '../src/utils/request'
beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
it('encodes parameters and sets isolated headers per request', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: 'success', data: {} })))
  vi.stubGlobal('fetch', fetch)
  await get('/apps', { params: { search_word: '知识 & AI', status: undefined } })
  expect(fetch.mock.calls[0][0]).toContain('search_word=%E7%9F%A5%E8%AF%86+%26+AI')
  expect(fetch.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer test-token')
})
it('unauthorized response rejects and redirects to login with original destination', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ code: 'unauthorized', message: '登录已过期' }), {
          status: 401,
        }),
      ),
  )
  await expect(get('/account')).rejects.toThrow('登录已过期')
  expect(mocked.clear).toHaveBeenCalledOnce()
  expect(mocked.replace).toHaveBeenCalledWith({
    path: '/auth/login',
    query: { redirect: '/web-apps/shared' },
  })
})
it('rejects HTTP 200 JSON errors on streaming endpoints', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ code: 'fail', message: 'Model unavailable' }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
  )
  await expect(
    ssePost('/apps/id/conversations', { body: { query: 'test' } }, () => {}),
  ).rejects.toThrow('Model unavailable')
})
it('aborts the network request on timeout', async () => {
  vi.useFakeTimers()
  let signal: AbortSignal
  vi.stubGlobal(
    'fetch',
    vi.fn((_url, { signal: s }) => {
      signal = s
      return new Promise((_resolve, reject) =>
        s.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))),
      )
    }),
  )
  const pending = post('/apps', { timeout: 20, body: { name: 'test' } })
  const check = expect(pending).rejects.toThrow('超时')
  await vi.advanceTimersByTimeAsync(20)
  await check
  expect(signal!.aborted).toBe(true)
})
