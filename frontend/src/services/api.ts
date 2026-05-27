import axios from 'axios'
import type { TripFormData, TripPlanResponse, TripPlan, TripListResponse, TripRecord, UserPreference, DiscoveredAttraction, DiscoveryStreamEvent, PlanFromSelectionsPayload, PreviewDayAssignmentResponse } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json'
  }
})

apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

export interface StreamEvent {
  type: 'init' | 'node_start' | 'node_complete' | 'complete' | 'error'
  message: string
  progress: number
  node?: string
  current_node?: string
  data?: TripPlan
}

export interface StreamOptions {
  timeout?: number
  signal?: AbortSignal
}

export async function generateTripPlanStream(
  formData: TripFormData,
  onEvent: (event: StreamEvent) => void,
  options?: StreamOptions
): Promise<void> {
  const timeout = options?.timeout || 180000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
      signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') {
      throw new Error('请求已取消或超时')
    }
    throw error
  }

  clearTimeout(timeoutId)

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('无法获取响应流')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event: StreamEvent = JSON.parse(trimmed.slice(6))
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') {
              return
            }
          } catch (e) {
            console.warn('解析SSE事件失败:', trimmed, e)
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}

export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export async function getTripList(params?: { status?: string; page?: number; page_size?: number }): Promise<TripListResponse> {
  const response = await apiClient.get<TripListResponse>('/api/trips', { params })
  return response.data
}

export async function getTripDetail(tripId: number): Promise<{ success: boolean; data: TripRecord }> {
  const response = await apiClient.get(`/api/trips/${tripId}`)
  return response.data
}

export async function saveTripToHistory(plan: TripPlan, request?: TripFormData): Promise<{ success: boolean; data: TripRecord; message: string }> {
  const response = await apiClient.post('/api/trips', { plan, request })
  return response.data
}

export async function deleteTripFromHistory(tripId: number): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete(`/api/trips/${tripId}`)
  return response.data
}

export async function updateTripStatus(tripId: number, status: string): Promise<{ success: boolean; data: TripRecord }> {
  const response = await apiClient.patch(`/api/trips/${tripId}/status`, { status })
  return response.data
}

export async function searchTrips(keyword: string, page?: number, pageSize?: number): Promise<TripListResponse> {
  const response = await apiClient.get<TripListResponse>('/api/trips/search', { params: { keyword, page, page_size: pageSize } })
  return response.data
}

export async function getUserPreferences(userId: string = 'default'): Promise<{ success: boolean; data?: UserPreference; message: string }> {
  const response = await apiClient.get(`/api/trip/preferences/${userId}`)
  return response.data
}

export async function updateUserPreferences(userId: string, preferences: UserPreference): Promise<{ success: boolean; data?: UserPreference; message: string }> {
  const response = await apiClient.put(`/api/trip/preferences/${userId}`, preferences)
  return response.data
}

export async function deleteUserPreferences(userId: string = 'default'): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete(`/api/trip/preferences/${userId}`)
  return response.data
}


export async function discoverAttractionsStream(
  formData: TripFormData,
  onEvent: (event: DiscoveryStreamEvent) => void,
  options?: StreamOptions
): Promise<void> {
  const timeout = options?.timeout || 300000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/discover/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
      signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') {
      throw new Error('请求已取消或超时')
    }
    throw error
  }

  clearTimeout(timeoutId)

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('无法获取响应流')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event: DiscoveryStreamEvent = JSON.parse(trimmed.slice(6))
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') {
              return
            }
          } catch (e) {
            console.warn('解析SSE事件失败:', trimmed, e)
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}


export async function searchAttractionManual(
  keywords: string,
  city: string
): Promise<{ success: boolean; data: DiscoveredAttraction[] }> {
  const response = await apiClient.post('/api/trip/discover/search', { keywords, city })
  return response.data
}


export async function planFromSelectionsStream(
  payload: PlanFromSelectionsPayload,
  onEvent: (event: StreamEvent) => void,
  options?: StreamOptions
): Promise<void> {
  const timeout = options?.timeout || 300000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/plan/from-selections/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') {
      throw new Error('请求已取消或超时')
    }
    throw error
  }

  clearTimeout(timeoutId)

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('无法获取响应流')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event: StreamEvent = JSON.parse(trimmed.slice(6))
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') {
              return
            }
          } catch (e) {
            console.warn('解析SSE事件失败:', trimmed, e)
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}


// ============ 草稿（骨架/详细分离）API ============

export interface DraftStreamEvent {
  type: 'init' | 'node_start' | 'node_complete' | 'progress' | 'complete' | 'error'
  message?: string
  progress?: number
  node?: string
  draft_id?: string
  data?: any
}

export async function createDraftFromSelectionsStream(
  formData: TripFormData,
  selectedAttractions: any[],
  dayAssignments: any[][] | null,
  weatherInfo: string,
  onEvent: (event: DraftStreamEvent) => void,
  options?: StreamOptions,
): Promise<void> {
  const timeout = options?.timeout || 240000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/draft/from-selections/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request: formData,
        selected_attractions: selectedAttractions,
        day_assignments: dayAssignments,
        weather_info: weatherInfo,
        user_id: 'default',
      }),
      signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') throw new Error('请求已取消或超时')
    throw error
  }
  clearTimeout(timeoutId)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)

  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法获取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event = JSON.parse(trimmed.slice(6)) as DraftStreamEvent
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') return
          } catch (e) {
            console.warn('解析 SSE 事件失败:', trimmed, e)
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}

export async function getDraft(draftId: string) {
  const resp = await apiClient.get(`/api/trip/draft/${draftId}`)
  return resp.data
}

export async function deleteDraft(draftId: string) {
  const resp = await apiClient.delete(`/api/trip/draft/${draftId}`)
  return resp.data
}

export interface DayEditBody {
  attractions_order?: string[]
  meals?: Array<Record<string, any>>
  day_start_time?: string
}

export async function assembleDay(
  draftId: string, dayIndex: number, body: DayEditBody = {}, force = false,
) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/assemble${force ? '?force=true' : ''}`,
    body,
  )
  return resp.data
}

export async function recomputeDay(
  draftId: string, dayIndex: number, body: DayEditBody,
) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/recompute`, body,
  )
  return resp.data
}

export async function aiRearrangeDay(
  draftId: string, dayIndex: number, hint?: string,
) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/ai-rearrange`,
    { hint: hint || null },
  )
  return resp.data
}

export async function rewriteNarrative(draftId: string, dayIndex: number) {
  const resp = await apiClient.post(
    `/api/trip/draft/${draftId}/day/${dayIndex}/narrative`, {},
  )
  return resp.data
}

export async function finalizeDraftStream(
  draftId: string,
  onEvent: (event: DraftStreamEvent) => void,
  options?: StreamOptions,
): Promise<void> {
  const timeout = options?.timeout || 180000
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  const signal = options?.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/trip/draft/${draftId}/finalize`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    })
  } catch (error: any) {
    clearTimeout(timeoutId)
    if (error.name === 'AbortError') throw new Error('请求已取消或超时')
    throw error
  }
  clearTimeout(timeoutId)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)

  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法获取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const event = JSON.parse(trimmed.slice(6)) as DraftStreamEvent
            onEvent(event)
            if (event.type === 'complete' || event.type === 'error') return
          } catch {}
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}


export async function previewDayAssignment(
  selectedAttractions: DiscoveredAttraction[],
  travelDays: number,
): Promise<PreviewDayAssignmentResponse> {
  const response = await apiClient.post<PreviewDayAssignmentResponse>(
    '/api/trip/plan/preview-day-assignment',
    {
      selected_attractions: selectedAttractions,
      travel_days: travelDays,
    },
    { timeout: 30000 },
  )
  return response.data
}

export interface LoadMoreRequest {
  city: string
  exclude_names: string[]
  batch_size?: number
  categories?: string[]
}

export interface LoadMoreResponse {
  attractions: DiscoveredAttraction[]
}

export async function loadMoreAttractions(req: LoadMoreRequest): Promise<LoadMoreResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/discover/load_more`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_size: 20, ...req }),
  })
  if (!resp.ok) {
    throw new Error(`加载更多失败: ${resp.status}`)
  }
  return resp.json() as Promise<LoadMoreResponse>
}

export default apiClient
