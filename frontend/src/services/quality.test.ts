import { afterEach, expect, it, vi } from 'vitest'
import { qualityGet } from './quality'
afterEach(() => { vi.unstubAllGlobals() })
it('uses only the matching in-memory cache on network failure and clears it when disabled', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ total: 70 })))
  vi.stubGlobal('fetch', fetcher)
  expect((await qualityGet<{total:number}>('/runs?test=cache')).stale).toBe(false)
  fetcher.mockRejectedValue(new TypeError('offline'))
  const cached = await qualityGet<{total:number}>('/runs?test=cache')
  expect(cached.stale).toBe(true); expect(cached.data.total).toBe(70)
  await expect(qualityGet('/runs?test=different')).rejects.toThrow('没有可用缓存')
  fetcher.mockResolvedValue(new Response(JSON.stringify({ enabled: false })))
  await qualityGet('/status')
  fetcher.mockRejectedValue(new TypeError('offline'))
  await expect(qualityGet('/runs?test=cache')).rejects.toThrow('没有可用缓存')
})
it('never substitutes cached records after forbidden or not found responses', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 })))
  vi.stubGlobal('fetch', fetcher); await qualityGet('/runs/test403')
  fetcher.mockResolvedValue(new Response('{}', { status: 403 }))
  await expect(qualityGet('/runs/test403')).rejects.toThrow('已关闭')
})
