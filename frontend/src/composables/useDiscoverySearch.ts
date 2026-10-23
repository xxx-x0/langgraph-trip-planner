import { onBeforeUnmount, ref } from 'vue'
import { discoverAttractionsStream } from '@/services/api'
import type { DiscoveryStreamEvent, TripFormData } from '@/types'

/** A cancelled or superseded stream must never replace the current choices. */
export function useDiscoverySearch(onEvent: (event: DiscoveryStreamEvent) => void) {
  const loading = ref(false)
  const loadingMessage = ref('')
  const loadingProgress = ref(0)
  const elapsedSeconds = ref(0)
  const discoveryNotice = ref('')
  let generation = 0
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setInterval> | undefined
  const clearTimer = () => { if (timer) clearInterval(timer); timer = undefined }

  function stopDiscovery() {
    generation++
    controller?.abort()
    clearTimer()
    loading.value = false
    discoveryNotice.value = '已停止搜索。已出现的景点和你的选择仍保留，可以继续手动添加或重新搜索。'
  }

  async function search(form: TripFormData) {
    const current = ++generation
    controller?.abort()
    controller = new AbortController()
    clearTimer()
    loading.value = true
    loadingMessage.value = '正在连接景点与天气服务'
    loadingProgress.value = 5
    elapsedSeconds.value = 0
    discoveryNotice.value = ''
    const started = Date.now()
    timer = setInterval(() => { elapsedSeconds.value = Math.floor((Date.now() - started) / 1000) }, 1000)
    try {
      await discoverAttractionsStream(form, event => {
        if (current !== generation) return
        if (event.type === 'progress') {
          loadingProgress.value = event.progress || 0
          loadingMessage.value = event.message || '正在查询景点详情'
        }
        if (event.type === 'error') discoveryNotice.value = event.message || '搜索失败，请重试。已有选择仍保留。'
        if (event.type === 'complete') loadingProgress.value = 100
        onEvent(event)
      }, { signal: controller.signal })
    } catch (error: any) {
      if (current === generation) discoveryNotice.value = error?.message || '搜索连接中断，可以重试。已有选择仍保留。'
    } finally {
      if (current === generation) { loading.value = false; clearTimer() }
    }
  }

  onBeforeUnmount(() => { generation++; controller?.abort(); clearTimer() })
  return { loading, loadingMessage, loadingProgress, elapsedSeconds, discoveryNotice, search, stopDiscovery }
}
