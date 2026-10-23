import { defineComponent } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDiscoverySearch } from './useDiscoverySearch'
const stream = vi.hoisted(() => vi.fn())
vi.mock('@/services/api', () => ({ discoverAttractionsStream: stream }))
afterEach(() => { vi.useRealTimers(); stream.mockReset() })

describe('discovery search recovery', () => {
  it('stops the wait, keeps choices, and ignores late events after retry', async () => {
    vi.useFakeTimers()
    const runs: any[] = []
    stream.mockImplementation((_form, callback, options) => new Promise(resolve => runs.push({ callback, options, resolve })))
    const event = vi.fn()
    let search!: ReturnType<typeof useDiscoverySearch>
    const wrapper = mount(defineComponent({ setup() { search = useDiscoverySearch(event); return () => null } }))
    const first = search.search({} as any)
    vi.advanceTimersByTime(61000)
    expect(search.elapsedSeconds.value).toBe(61)
    search.stopDiscovery()
    expect(runs[0].options.signal.aborted).toBe(true)
    expect(search.discoveryNotice.value).toContain('选择仍保留')
    const second = search.search({} as any)
    runs[0].callback({ type: 'attraction', data: { name: '旧请求景点' } })
    expect(event).not.toHaveBeenCalled()
    runs[1].callback({ type: 'attraction', data: { name: '新请求景点' } })
    expect(event).toHaveBeenCalledOnce()
    runs[0].resolve(); await first
    expect(search.loading.value).toBe(true)
    runs[1].resolve(); await second
    expect(search.loading.value).toBe(false)
    vi.advanceTimersByTime(5000)
    expect(search.elapsedSeconds.value).toBe(0)
    wrapper.unmount()
  })
  it('keeps connection failure visible and cancels on leaving the page', async () => {
    stream.mockRejectedValueOnce(new Error('连接中断'))
    let search!: ReturnType<typeof useDiscoverySearch>
    const wrapper = mount(defineComponent({ setup() { search = useDiscoverySearch(vi.fn()); return () => null } }))
    await search.search({} as any)
    expect(search.discoveryNotice.value).toBe('连接中断')
    expect(search.loading.value).toBe(false)
    let signal: AbortSignal
    stream.mockImplementation((_form, _callback, options) => new Promise((_resolve, reject) => {
      signal = options.signal
      signal.addEventListener('abort', () => reject(new Error('aborted')))
    }))
    const pending = search.search({} as any)
    wrapper.unmount()
    expect(signal!.aborted).toBe(true)
    await pending
    await flushPromises()
  })
})
