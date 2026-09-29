export interface StreamFrame {
  event: string
  data: Record<string, any>
}
export const terminalEvents = new Set(['agent_end', 'error', 'stop', 'timeout'])

/** Decode complete SSE frames only; never parse an unfinished network chunk. */
export async function readSSE(
  response: Response,
  onFrame: (frame: StreamFrame) => void,
  requireTerminal = true,
) {
  if (!response.body) throw new Error('服务器未返回可读取的数据流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = '',
    ended = false
  const consume = (raw: string) => {
    let event = 'message'
    const data: string[] = []
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!data.length) return
    let payload: Record<string, any>
    try {
      payload = JSON.parse(data.join('\n'))
    } catch {
      throw new Error('服务器返回了无效的流式数据')
    }
    onFrame({ event, data: payload })
    if (terminalEvents.has(event)) ended = true
  }
  try {
    while (!ended) {
      const { value, done } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let match: RegExpMatchArray | null
      while (!ended && (match = buffer.match(/\r?\n\r?\n/))) {
        const i = match.index!
        consume(buffer.slice(0, i))
        buffer = buffer.slice(i + match[0].length)
      }
      if (done) {
        if (buffer.trim()) throw new Error('连接在事件接收完成前中断，已保留收到的内容')
        if (requireTerminal && !ended) throw new Error('连接意外结束，已保留收到的内容')
        break
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
