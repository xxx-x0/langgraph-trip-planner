import { reactive, readonly } from 'vue'

export type LoaderPoster = 'construction' | 'refinement'
export type LoaderPhase = 'idle' | 'entering' | 'steady' | 'flipping'

export interface LoaderContext {
  city: string
  days: number
  attractionCount: number
  weatherSummary?: string
}

interface LoaderStore {
  phase: LoaderPhase
  poster: LoaderPoster | null
  context: LoaderContext | null
  currentNode: string
  currentMessage: string
  progress: number
}

// 模块级单例：所有调用方共享同一份状态
const store = reactive<LoaderStore>({
  phase: 'idle',
  poster: null,
  context: null,
  currentNode: '',
  currentMessage: '',
  progress: 0,
})

function reset(): void {
  store.phase = 'idle'
  store.poster = null
  store.context = null
  store.currentNode = ''
  store.currentMessage = ''
  store.progress = 0
}

export function useTripLoader() {
  function begin(poster: LoaderPoster, context: LoaderContext): void {
    store.poster = poster
    store.context = context
    store.currentNode = ''
    store.currentMessage = ''
    store.progress = 0
    store.phase = 'entering'
  }

  function setSteady(): void {
    if (store.phase === 'entering') store.phase = 'steady'
  }

  function updateProgress(node: string, message: string, progress: number): void {
    store.currentNode = node
    store.currentMessage = message
    store.progress = progress
  }

  function markReady(): void {
    if (store.phase === 'entering' || store.phase === 'steady') {
      store.phase = 'flipping'
    }
  }

  function finishFlip(): void {
    reset()
  }

  function dismiss(): void {
    reset()
  }

  return {
    state: readonly(store),
    begin,
    setSteady,
    updateProgress,
    markReady,
    finishFlip,
    dismiss,
    reset,
  }
}
