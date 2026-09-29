import { describe, it, expect } from 'vitest'
import { readSSE } from '../src/utils/sse'
import { applyChatFrame, usageLabel, type ChatMessage } from '../src/utils/chat'
const response = (text: string, split = 1) => {
  const bytes = new TextEncoder().encode(text)
  return new Response(
    new ReadableStream({
      start(c) {
        for (let i = 0; i < bytes.length; i += split) c.enqueue(bytes.slice(i, i + split))
        c.close()
      },
    }),
  )
}
describe('SSE network boundaries', () => {
  it('decodes byte-split Chinese and ignores frames after terminal', async () => {
    const events: any[] = []
    await readSSE(
      response(
        'event: agent_message\r\ndata: {"answer":"你好"}\r\n\r\nevent: agent_end\ndata: {}\n\nevent: agent_message\ndata: {"answer":"late"}\n\n',
      ),
      (e) => events.push(e),
    )
    expect(events.map((e) => e.event)).toEqual(['agent_message', 'agent_end'])
    expect(events[0].data.answer).toBe('你好')
  })
  it.each(['agent_end', 'stop', 'timeout', 'error'])('closes on %s', async (event) => {
    const events: any[] = []
    await readSSE(response(`event: ${event}\ndata: {}\n\n`), (e) => events.push(e))
    expect(events).toHaveLength(1)
  })
  it('supports multiline JSON data', async () => {
    const events: any[] = []
    await readSSE(response('event: agent_end\ndata: {"usage":\ndata: null}\n\n'), (e) =>
      events.push(e),
    )
    expect(events[0].data.usage).toBeNull()
  })
  it('rejects EOF without a terminal', async () => {
    await expect(readSSE(response('event: ping\ndata: {}\n\n'), () => {})).rejects.toThrow(
      '连接意外结束',
    )
  })
  it('rejects incomplete last frame', async () => {
    await expect(readSSE(response('event: agent_message\ndata: {'), () => {})).rejects.toThrow(
      '中断',
    )
  })
  it('rejects invalid JSON', async () => {
    await expect(
      readSSE(response('event: agent_end\ndata: invalid\n\n'), () => {}),
    ).rejects.toThrow('无效')
  })
  it('allows workflow EOF', async () => {
    await expect(
      readSSE(response('event: workflow\ndata: {"status":"succeeded"}\n\n'), () => {}, false),
    ).resolves.toBeUndefined()
  })
})
describe('usage and answer merging', () => {
  it('appends text, replaces settlement and preserves errors', () => {
    const message: ChatMessage = { id: '', query: 'hi', answer: '', agent_thoughts: [] }
    applyChatFrame(message, {
      event: 'agent_message',
      data: { id: '1', answer: 'Hello', usage: null },
    })
    applyChatFrame(message, {
      event: 'agent_message',
      data: { id: '1', answer: ' world', usage: null },
    })
    for (let i = 0; i < 2; i++)
      applyChatFrame(message, {
        event: 'agent_message',
        data: { id: '1', answer: '', total_token_count: 20, usage: { total_price: '0.001' } },
      })
    applyChatFrame(message, {
      event: 'error',
      data: {
        observation: 'Provider rejected request',
        usage: { total_price: null, complete: false },
      },
    })
    expect(message.answer).toBe('Hello world')
    expect(message.agent_thoughts).toHaveLength(1)
    expect(message.agent_thoughts[0].total_token_count).toBe(20)
    expect(message.error).toBe('Provider rejected request')
    expect(usageLabel(message.usage)).toContain('费用未知')
    expect(usageLabel(message.usage)).toContain('不完整')
  })
})
