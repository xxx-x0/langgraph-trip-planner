import { afterEach, describe, expect, it, vi } from 'vitest'
import { postSSE } from './sse'

function response(text: string) {
  return new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(text)); c.close() } }))
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('stream recovery', () => {
  it('rejects EOF before complete and retains the last failed stage', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response('data: {"type":"progress","step":"search_weather"}\n\n')))
    const event = vi.fn()
    await expect(postSSE('/api',{},event)).rejects.toThrow('查询天气')
    expect(event).toHaveBeenCalledOnce()
  })

  it('handles split frames, CRLF and a complete event without a trailing newline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(': heartbeat\r\n\r\ndata:{"type":"complete","draft_id":"kept"}')))
    const event = vi.fn()
    await postSSE('/api',{},event)
    expect(event).toHaveBeenCalledWith({ type:'complete', draft_id:'kept' })
  })

  it('keeps the deadline active after response headers and cancels a stalled body', async () => {
    vi.useFakeTimers()
    const cancel = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }))))
    const pending = postSSE('/api',{},vi.fn(),{ timeout:50 })
    const rejected = expect(pending).rejects.toThrow('超时')
    await vi.advanceTimersByTimeAsync(60)
    await rejected
    expect(cancel).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not hide callback exceptions as JSON failures', async () => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response('data: {"type":"complete"}\n\n')))
    await expect(postSSE('/api',{},()=>{ throw new Error('render failed') })).rejects.toThrow('render failed')
  })

  it('reports malformed data and handles user cancellation', async () => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response('data: broken\n\n')))
    await expect(postSSE('/api',{},vi.fn())).rejects.toThrow('无法解析')
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(new ReadableStream())))
    const controller=new AbortController()
    const pending=postSSE('/api',{},vi.fn(),{ signal:controller.signal })
    controller.abort()
    await expect(pending).rejects.toThrow('取消')
  })
})
