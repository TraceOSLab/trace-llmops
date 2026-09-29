import { reactive } from 'vue'
export function createDraftQueue() {
  const state = reactive({ pending: 0, error: '', savedAt: 0 })
  const scheduled = new Map<
    string,
    { timer: ReturnType<typeof setTimeout>; write: () => Promise<unknown> }
  >()
  let tail: Promise<unknown> = Promise.resolve()
  let blocked: Array<() => Promise<unknown>> = []
  function enqueue<T>(write: () => Promise<T>): Promise<T> {
    state.pending++
    const result = tail
      .catch(() => {})
      .then(async () => {
        // Preserve later patches behind a failed write, so retry cannot restore an older value.
        if (state.error) {
          blocked.push(write)
          throw new Error(state.error)
        }
        try {
          const value = await write()
          state.savedAt = Date.now()
          return value
        } catch (error: any) {
          blocked.push(write)
          state.error = error.message || '保存失败'
          throw error
        }
      })
      .finally(() => {
        state.pending--
      })
    tail = result
    void result.catch(() => {})
    return result
  }
  function schedule(key: string, write: () => Promise<unknown>, delay = 350) {
    const previous = scheduled.get(key)
    if (previous) clearTimeout(previous.timer)
    else state.pending++
    const run = () => {
      const item = scheduled.get(key)
      if (!item) return
      clearTimeout(item.timer)
      scheduled.delete(key)
      state.pending--
      void enqueue(item.write).catch(() => {})
    }
    scheduled.set(key, { write, timer: setTimeout(run, delay) })
  }
  async function flush() {
    for (const [key, item] of scheduled) {
      clearTimeout(item.timer)
      scheduled.delete(key)
      state.pending--
      void enqueue(item.write).catch(() => {})
    }
    await tail
    if (state.error) throw new Error(state.error)
  }
  async function retry() {
    await tail.catch(() => {})
    const retained = blocked
    blocked = []
    state.error = ''
    const writes = retained.map((write) => enqueue(write))
    await Promise.all(writes)
  }
  return { state, enqueue, flush, retry, schedule }
}
const appQueues = new Map<string, ReturnType<typeof createDraftQueue>>()
export function appDraftQueueFor(id: string) {
  if (!appQueues.has(id)) appQueues.set(id, createDraftQueue())
  return appQueues.get(id)!
}
export const workflowDraftQueue = createDraftQueue()
