import type {
  MemoryCity,
  MemoryDate,
  MemoryFootprint,
  MemoryForm,
  MemoryPhoto,
  TravelMemory,
} from '@/types/travelMemory'

export const memoryId = () => crypto.randomUUID().replace(/-/g, '')
export const unknownDate = (): MemoryDate => ({
  precision: 'unknown',
  start: '',
  end: '',
})
export const emptyMemoryForm = (): MemoryForm => ({
  title: '',
  note: '',
  when: unknownDate(),
  visits: [],
  moments: [],
  photos: [],
  cover_photo_id: null,
})
export function formatMemoryDate(value: MemoryDate): string {
  if (!value || value.precision === 'unknown' || !value.start) return '日期未记'
  const suffix = value.precision === 'year' ? ' 年' : ''
  return (
    value.start +
    (value.end && value.end !== value.start ? ' — ' + value.end : '') +
    suffix
  )
}
export function cityKey(city: MemoryCity) {
  return [city.country, city.region, city.city].join('|')
}
export function footprints(records: TravelMemory[]): MemoryFootprint[] {
  const map = new Map<string, MemoryFootprint>()
  for (const record of records.filter((r) => !r.document.deleted))
    for (const visit of record.document.visits) {
      const key = cityKey(visit)
      if (!map.has(key))
        map.set(key, { ...visit, key, recordIds: [], visits: 0 })
      const point = map.get(key)!
      point.visits++
      if (!point.recordIds.includes(record.id)) point.recordIds.push(record.id)
      if (point.latitude === null && visit.latitude !== null) {
        point.latitude = visit.latitude
        point.longitude = visit.longitude
      }
    }
  return [...map.values()].sort(
    (a, b) =>
      b.recordIds.length - a.recordIds.length ||
      a.city.localeCompare(b.city, 'zh-CN'),
  )
}
export function coverPhoto(record: TravelMemory): MemoryPhoto | undefined {
  const photos = record.document.photos.filter((p) => !p.deleted)
  return (
    photos.find((p) => p.id === record.document.cover_photo_id) || photos[0]
  )
}
export function formFromRecord(record: TravelMemory): MemoryForm {
  const d = record.document
  return JSON.parse(
    JSON.stringify({
      title: d.title,
      note: d.note,
      when: d.when,
      visits: d.visits,
      moments: d.moments,
      cover_photo_id: d.cover_photo_id,
      photos: d.photos.map(
        ({ id, caption, moment_id, deleted, focal_x, focal_y }) => ({
          id,
          caption,
          moment_id,
          deleted,
          focal_x,
          focal_y,
        }),
      ),
    }),
  )
}
export function recordMatchesYear(record: TravelMemory, year: string): boolean {
  if (!year) return true
  const when = record.document.when
  if (year === 'unknown') return when.precision === 'unknown'
  return (
    when.precision !== 'unknown' &&
    year >= when.start.slice(0, 4) &&
    year <= (when.end || when.start).slice(0, 4)
  )
}
export function mergePhotoEdits(
  local: MemoryForm,
  server: TravelMemory,
): MemoryForm {
  const form = JSON.parse(JSON.stringify(local)) as MemoryForm
  const saved = formFromRecord(server)
  const existingIds = new Set(saved.photos.map((p) => p.id))
  form.photos = [
    ...form.photos.filter((p) => existingIds.has(p.id)),
    ...saved.photos.filter((p) => !form.photos.some((x) => x.id === p.id)),
  ]
  for (const photo of form.photos)
    if (photo.moment_id && !form.moments.some((m) => m.id === photo.moment_id))
      photo.moment_id = null
  if (
    form.cover_photo_id &&
    !form.photos.some((p) => p.id === form.cover_photo_id && !p.deleted)
  )
    form.cover_photo_id = null
  return form
}
