import { describe, expect, it } from 'vitest'
import { multiTripInputIssues } from './multiTripValidation'
const plan = () => ({ title: '苏杭慢旅行', start_date: '2026-10-27', end_date: '2026-10-31',
  stops: [
    { id: 's', city: {name: '苏州'}, start_date: '2026-10-27', end_date: '2026-10-29' },
    { id: 'h', city: {name: '杭州'}, start_date: '2026-10-29', end_date: '2026-10-31' },
  ] })
describe('multi-trip date feedback', () => {
  it('allows a same-day city change and overnight gaps', () => {
    const value = plan()
    expect(multiTripInputIssues(value)).toEqual([])
    value.stops[1].start_date = '2026-10-30'
    expect(multiTripInputIssues(value)).toEqual([])
  })
  it('points to the city that falls outside a shortened trip', () => {
    const value = plan()
    value.stops[1].end_date = '2026-11-02'
    expect(multiTripInputIssues(value)).toEqual([{field: 'city-end-h', message: '杭州离开日期超出旅行范围，请调整到 2026-10-31 或之前。'}])
  })
  it('identifies missing dates, reversed stays and overlaps before a request', () => {
    const value = plan()
    value.stops[0].end_date = '2026-10-30'
    value.stops[1].end_date = '2026-10-28'
    expect(multiTripInputIssues(value).map(i => i.field)).toEqual(['city-end-h', 'city-start-h'])
    value.start_date = ''
    expect(multiTripInputIssues(value)[0].field).toBe('trip-start')
  })
})
