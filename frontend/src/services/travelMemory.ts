import type {
  MemoryCity,
  MemoryForm,
  MemorySource,
  MemorySourceRef,
  RestorePreview,
  SourceSummary,
  TravelMemory,
} from '@/types/travelMemory'

const base = (import.meta.env.VITE_API_BASE_URL || '') + '/api/travel-records'
export class MemoryApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}
async function request<T>(
  path: string,
  init: RequestInit = {},
  binary = false,
): Promise<T> {
  const abort = new AbortController()
  const timeout = setTimeout(
    () => abort.abort(),
    binary || init.body instanceof FormData || path === '/restore/confirm'
      ? 300000
      : 30000,
  )
  try {
    const response = await fetch(base + path, {
      ...init,
      signal: abort.signal,
      headers: {
        ...(typeof init.body === 'string'
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...init.headers,
      },
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      const detail = Array.isArray(body.detail)
        ? body.detail.map((e: { msg: string }) => e.msg).join('；')
        : body.detail
      throw new MemoryApiError(
        typeof detail === 'string' ? detail : '操作未完成，请稍后重试',
        response.status,
      )
    }
    return (binary ? await response.blob() : await response.json()) as T
  } catch (error) {
    if (error instanceof MemoryApiError) throw error
    throw new MemoryApiError(
      abort.signal.aborted
        ? '请求超时，未确认操作结果；请恢复连接后重试'
        : '暂时无法连接服务，请恢复连接后重试',
      0,
    )
  } finally {
    clearTimeout(timeout)
  }
}
export const memoryApi = {
  list: () => request<TravelMemory[]>(''),
  get: (id: string) => request<TravelMemory>('/' + encodeURIComponent(id)),
  cities: (q: string) =>
    request<MemoryCity[]>('/cities?q=' + encodeURIComponent(q)),
  sources: (q = '', offset = 0) =>
    request<{ items: SourceSummary[]; total: number }>(
      '/sources?q=' + encodeURIComponent(q) + '&offset=' + offset,
    ),
  source: (kind: string, id: string) =>
    request<MemorySource>(
      '/sources/' + encodeURIComponent(kind) + '/' + encodeURIComponent(id),
    ),
  create: (id: string, form: MemoryForm, source: MemorySourceRef | null) => {
    const { photos, cover_photo_id, ...data } = form
    return request<TravelMemory>('', {
      method: 'POST',
      body: JSON.stringify({
        ...data,
        id,
        source,
        confirmed_visit_ids: source ? data.visits.map((v) => v.id) : [],
      }),
    })
  },
  update: (
    id: string,
    revision: number,
    form: MemoryForm,
    operation_id: string,
  ) =>
    request<TravelMemory>('/' + id, {
      method: 'PUT',
      body: JSON.stringify({ ...form, revision, operation_id }),
    }),
  trash: (record: TravelMemory, deleted: boolean) =>
    request<TravelMemory>('/' + record.id + '/trash', {
      method: 'PATCH',
      body: JSON.stringify({ revision: record.revision, deleted }),
    }),
  upload: (id: string, revision: number, photoId: string, file: File) => {
    const data = new FormData()
    data.append('revision', String(revision))
    data.append('photo_id', photoId)
    data.append('file', file)
    return request<TravelMemory>('/' + id + '/photos', {
      method: 'POST',
      body: data,
    })
  },
  backup: () => request<Blob>('/backup', {}, true),
  previewRestore: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<RestorePreview>('/restore/preview', { method: 'POST', body })
  },
  restore: (token: string, conflicts: 'copy' | 'skip') =>
    request<{ added: number; copied: number; skipped: number }>(
      '/restore/confirm',
      { method: 'POST', body: JSON.stringify({ token, conflicts }) },
    ),
}
export const photoUrl = (
  recordId: string,
  photoId: string,
  preview = true,
  download = false,
) =>
  base +
  '/' +
  encodeURIComponent(recordId) +
  '/photos/' +
  encodeURIComponent(photoId) +
  '?preview=' +
  preview +
  '&download=' +
  download
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob),
    link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
