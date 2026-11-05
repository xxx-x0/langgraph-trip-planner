export type DatePrecision = 'unknown' | 'year' | 'month' | 'day'
export interface MemoryDate {
  precision: DatePrecision
  start: string
  end: string
}
export interface MemoryCity {
  city: string
  country: string
  region: string
  latitude: number | null
  longitude: number | null
  search?: string
}
export interface MemoryVisit extends MemoryCity {
  id: string
  when: MemoryDate
}
export interface MemoryMoment {
  id: string
  title: string
  text: string
  place: string
  visit_id: string | null
  when: MemoryDate
  deleted: boolean
}
export interface MemoryPhotoEdit {
  id: string
  caption: string
  moment_id: string | null
  deleted: boolean
  focal_x: number
  focal_y: number
}
export interface MemoryPhoto extends MemoryPhotoEdit {
  sha256: string
  filename: string
  media_type: string
  size: number
  width: number
  height: number
}
export interface MemorySourceRef {
  kind: 'single' | 'multi'
  id: string
  title: string
  basis: string
}
export interface MemoryDocument {
  title: string
  note: string
  when: MemoryDate
  visits: MemoryVisit[]
  moments: MemoryMoment[]
  photos: MemoryPhoto[]
  cover_photo_id: string | null
  source: MemorySourceRef | null
  deleted: boolean
}
export interface TravelMemory {
  id: string
  revision: number
  created_at: string
  updated_at: string
  document: MemoryDocument
}
export interface MemoryForm {
  title: string
  note: string
  when: MemoryDate
  visits: MemoryVisit[]
  moments: MemoryMoment[]
  photos: MemoryPhotoEdit[]
  cover_photo_id: string | null
}
export interface SourceSummary {
  kind: 'single' | 'multi'
  id: string
  title: string
  cities: string[]
  start: string
  end: string
}
export interface MemorySource extends MemorySourceRef {
  visits: (MemoryVisit & { planned_start: string; planned_end: string })[]
}
export interface PendingPhoto {
  id: string
  file: File
  error: string
}
export interface MemoryDraft {
  key: string
  id: string
  serverId: string | null
  revision: number
  form: MemoryForm
  source: MemorySourceRef | null
  operationId: string
  pending: PendingPhoto[]
  updated: number
  cachedRecord?: TravelMemory
}
export interface RestorePreview {
  token: string
  items: {
    id: string
    title: string
    deleted: boolean
    status: 'new' | 'identical' | 'conflict' | 'already_restored'
    photos: number
  }[]
  counts: Record<string, number>
  photo_files_to_restore: number
  expires_in_seconds: number
}
export interface MemoryFootprint extends MemoryCity {
  key: string
  recordIds: string[]
  visits: number
}
