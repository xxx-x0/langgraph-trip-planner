import { describe, it, expect } from 'vitest'
import {
  cityKey,
  coverPhoto,
  emptyMemoryForm,
  footprints,
  formFromRecord,
  mergePhotoEdits,
  recordMatchesYear,
  unknownDate,
} from './travelMemory'
import {
  createFocusedGlobeView,
  projectTravelGlobeLocation,
} from './memoryGlobe'
import type { TravelMemory, MemoryPhoto } from '@/types/travelMemory'
const photo = (id: string, deleted = false): MemoryPhoto => ({
  id,
  deleted,
  caption: '',
  moment_id: null,
  focal_x: 50,
  focal_y: 50,
  sha256: 'a'.repeat(64),
  filename: 'test.jpg',
  media_type: 'image/jpeg',
  size: 100,
  width: 20,
  height: 10,
})
const record = (id: string): TravelMemory => ({
  id,
  revision: 1,
  created_at: '',
  updated_at: '',
  document: {
    ...emptyMemoryForm(),
    photos: [],
    source: null,
    deleted: false,
    visits: [
      {
        id: 'visit',
        city: '杭州',
        region: '浙江',
        country: '中国',
        latitude: 30,
        longitude: 120,
        when: unknownDate(),
      },
    ],
  },
})
describe('actual travel memories', () => {
  it('counts cities, trips and repeated visits separately, excluding trash', () => {
    const a = record('a'),
      b = record('b'),
      deleted = record('deleted')
    deleted.document.deleted = true
    a.document.visits.push({ ...a.document.visits[0], id: 'again' })
    const result = footprints([a, b, deleted])
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({ visits: 3, recordIds: ['a', 'b'] })
  })
  it('keeps unlocated cities and uses later known coordinates without inventing a location', () => {
    const a = record('a'),
      b = record('b')
    a.document.visits[0].latitude = null
    a.document.visits[0].longitude = null
    expect(footprints([a])[0].latitude).toBeNull()
    expect(footprints([a, b])[0].latitude).toBe(30)
    expect(cityKey(a.document.visits[0])).toBe(cityKey(b.document.visits[0]))
  })
  it('filters partial dates across years while leaving unknown dates unknown', () => {
    const a = record('a')
    expect(recordMatchesYear(a, 'unknown')).toBe(true)
    expect(recordMatchesYear(a, '2020')).toBe(false)
    a.document.when = { precision: 'month', start: '2020-12', end: '2021-02' }
    expect(recordMatchesYear(a, '2020')).toBe(true)
    expect(recordMatchesYear(a, '2021')).toBe(true)
    expect(recordMatchesYear(a, '2022')).toBe(false)
  })
  it('only uses active cover photos and isolates editing from saved metadata', () => {
    const a = record('a')
    a.document.photos = [photo('a', true), photo('b')]
    a.document.cover_photo_id = 'a'
    expect(coverPhoto(a)?.id).toBe('b')
    const form = formFromRecord(a)
    form.photos[1].caption = 'new'
    form.visits[0].city = 'new'
    expect(a.document.photos[1].caption).toBe('')
    expect(a.document.visits[0].city).toBe('杭州')
    expect(form.photos[1]).not.toHaveProperty('sha256')
  })
  it('conflict review retains local order and captions, includes new photos, and clears missing moment links', () => {
    const a = record('a')
    a.document.photos = [photo('first'), photo('second')]
    const form = formFromRecord(a)
    form.photos.reverse()
    form.photos[0].caption = 'my edit'
    a.document.photos.push({
      ...photo('new'),
      moment_id: 'other-editor-moment',
    })
    const merged = mergePhotoEdits(form, a)
    expect(merged.photos.map((p) => p.id)).toEqual(['second', 'first', 'new'])
    expect(merged.photos[0].caption).toBe('my edit')
    expect(merged.photos[2].moment_id).toBeNull()
  })
  it.each([
    { latitude: 30.2741, longitude: 120.1551 },
    { latitude: 48.853, longitude: 2.349 },
    { latitude: -33.86, longitude: 151.2 },
  ])('focuses an actual city onto the visible globe: %j', (location) => {
    const result = projectTravelGlobeLocation(
      location,
      createFocusedGlobeView(location),
    )
    expect(result.depth).toBeGreaterThan(0.99)
    expect(Math.abs(result.x)).toBeLessThan(0.01)
  })
})
