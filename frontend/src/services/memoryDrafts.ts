import type { MemoryDraft } from '@/types/travelMemory'

// IndexedDB retains File objects as well as text; localStorage never holds originals.
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('lets-go-travel-memory-drafts', 1)
    request.onupgradeneeded = () =>
      request.result.createObjectStore('drafts', { keyPath: 'key' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    request.onblocked = () =>
      reject(new Error('本机草稿库被其他窗口占用，请关闭旧窗口后重试'))
  })
}
async function transaction<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('drafts', mode)
    let result: T
    const req = action(tx.objectStore('drafts'))
    req.onsuccess = () => {
      result = req.result
    }
    tx.oncomplete = () => {
      db.close()
      resolve(result)
    }
    tx.onerror = tx.onabort = () => {
      db.close()
      reject(tx.error || req.error || new Error('本机草稿未能保存'))
    }
  })
}
export const memoryDrafts = {
  get: (key: string) =>
    transaction<MemoryDraft | undefined>('readonly', (s) => s.get(key)),
  list: () => transaction<MemoryDraft[]>('readonly', (s) => s.getAll()),
  put: (draft: MemoryDraft) => transaction('readwrite', (s) => s.put(draft)),
  remove: (key: string) => transaction('readwrite', (s) => s.delete(key)),
}
