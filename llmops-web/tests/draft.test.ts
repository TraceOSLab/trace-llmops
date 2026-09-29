import { describe, it, expect } from 'vitest'
import { createDraftQueue } from '../src/utils/draft-queue'
describe('serial draft writes', () => {
  it('keeps writes ordered and flush waits for all', async () => {
    const queue = createDraftQueue(),
      writes: string[] = []
    let release!: () => void
    const first = queue.enqueue(async () => {
      await new Promise<void>((r) => (release = r))
      writes.push('old')
    })
    const second = queue.enqueue(async () => {
      writes.push('new')
    })
    await new Promise((r) => setTimeout(r, 0))
    expect(writes).toEqual([])
    release()
    await queue.flush()
    await Promise.all([first, second])
    expect(writes).toEqual(['old', 'new'])
    expect(queue.state.pending).toBe(0)
  })
  it('blocks publishing after failure and retries retained write', async () => {
    const queue = createDraftQueue()
    let fail = true
    await expect(
      queue.enqueue(async () => {
        if (fail) throw new Error('offline')
      }),
    ).rejects.toThrow('offline')
    await expect(queue.flush()).rejects.toThrow('offline')
    expect(queue.state.error).toBe('offline')
    fail = false
    await queue.retry()
    await queue.flush()
    expect(queue.state.error).toBe('')
  })
})
it('retains later patches behind an error and retries them in order', async () => {
  const queue = createDraftQueue(),
    writes: string[] = []
  let fail = true
  const old = queue.enqueue(async () => {
    if (fail) throw new Error('offline')
    writes.push('old')
  })
  const latest = queue.enqueue(async () => {
    writes.push('latest')
  })
  await Promise.allSettled([old, latest])
  expect(writes).toEqual([])
  fail = false
  await queue.retry()
  expect(writes).toEqual(['old', 'latest'])
})
it('flush drains debounced edits before publish', async () => {
  const queue = createDraftQueue(),
    writes: string[] = []
  queue.schedule(
    'prompt',
    async () => {
      writes.push('old')
    },
    10000,
  )
  queue.schedule(
    'prompt',
    async () => {
      writes.push('current')
    },
    10000,
  )
  expect(queue.state.pending).toBe(1)
  await queue.flush()
  expect(writes).toEqual(['current'])
  expect(queue.state.pending).toBe(0)
})
