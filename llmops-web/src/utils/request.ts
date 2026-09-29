import { Message } from '@arco-design/web-vue'
import { apiPrefix } from '@/config'
import { useCredentialStore } from '@/stores/credential'
import router from '@/router'
import { readSSE } from './sse'

export class ApiError extends Error {
  constructor(
    message: string,
    public code = 'fail',
    public status = 0,
  ) {
    super(message)
  }
}
type Options = Omit<RequestInit, 'body'> & {
  params?: Record<string, any>
  body?: any
  timeout?: number
}
const urlFor = (path: string, params?: Record<string, any>) => {
  const query = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null) query.set(key, String(value))
  })
  return `${apiPrefix}${path.startsWith('/') ? path : '/' + path}${query.size ? '?' + query : ''}`
}
async function fail(message: string, code: string, status = 0): Promise<never> {
  if (code === 'unauthorized' || status === 401) {
    useCredentialStore().clear()
    const redirect = router.currentRoute.value.fullPath
    if (!redirect.startsWith('/auth/'))
      await router.replace({ path: '/auth/login', query: { redirect } })
  }
  throw new ApiError(message, code, status)
}
async function send(
  path: string,
  options: Options,
  stream = false,
  onData?: (data: any) => void,
): Promise<any> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) controller.abort()
  const timer = setTimeout(abort, options.timeout ?? (stream ? 600000 : 100000))
  const headers = new Headers(options.headers)
  const token = useCredentialStore().credential.access_token
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const isForm = options.body instanceof FormData
  if (!isForm) headers.set('Content-Type', 'application/json')
  try {
    const response = await fetch(urlFor(path, options.params), {
      method: options.method || 'GET',
      credentials: 'include',
      headers,
      signal: controller.signal,
      body: options.body == null ? undefined : isForm ? options.body : JSON.stringify(options.body),
    })
    if (
      stream &&
      response.ok &&
      response.headers.get('Content-Type')?.includes('text/event-stream')
    ) {
      return await readSSE(
        response,
        onData!,
        !path.includes('/workflows/') && !path.includes('optimize-prompt'),
      )
    }
    const json = await response
      .json()
      .catch(() => ({ message: `请求失败（HTTP ${response.status}）` }))
    if (!response.ok || json.code !== 'success')
      await fail(json.message || '请求失败，请稍后重试', json.code, response.status)
    if (stream) throw new ApiError('服务器未返回预期的数据流')
    return json
  } catch (error: any) {
    const normalized = error.name === 'AbortError' ? new ApiError('请求已取消或超时') : error
    Message.error(normalized.message || '网络连接失败')
    throw normalized
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}
export const request = <T>(url: string, options: Options = {}): Promise<T> => send(url, options)
export const get = <T>(url: string, options: Options = {}) =>
  request<T>(url, { ...options, method: 'GET' })
export const post = <T>(url: string, options: Options = {}) =>
  request<T>(url, { ...options, method: 'POST' })
export const ssePost = (url: string, options: Options, onData: (data: any) => void): Promise<any> =>
  send(url, { ...options, method: 'POST' }, true, onData)
export const upload = <T>(url: string, options: any = {}): Promise<T> =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', urlFor(url))
    xhr.withCredentials = true
    xhr.responseType = 'json'
    xhr.timeout = 100000
    const token = useCredentialStore().credential.access_token
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    if (options.onprogress) xhr.upload.onprogress = options.onprogress
    xhr.onload = async () => {
      const data = xhr.response
      if (xhr.status >= 200 && xhr.status < 300 && data?.code === 'success') resolve(data)
      else {
        try {
          await fail(data?.message || '上传失败', data?.code, xhr.status)
        } catch (e) {
          reject(e)
        }
      }
    }
    xhr.onerror = () => reject(new ApiError('上传失败，请检查网络'))
    xhr.ontimeout = () => reject(new ApiError('上传超时，请重试'))
    xhr.onabort = () => reject(new ApiError('上传已取消'))
    xhr.send(options.data)
  })
