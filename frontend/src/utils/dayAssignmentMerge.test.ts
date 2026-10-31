import { describe, expect, it } from 'vitest'
import { mergeDayAssignmentsWithSelected, hasUnsupportedEmptyDay } from './dayAssignmentMerge'

describe('mergeDayAssignmentsWithSelected', () => {
  it('preserves cached attraction fields when preview returns slim day assignments', () => {
    const selected = [
      {
        name: '寒山寺',
        address: '枫桥路16号',
        rating: 4.8,
        image_url: 'http://store.is.autonavi.com/showpic/hanshan',
        open_hours: '08:00-17:00',
        tel: '0512-00000000',
      },
      {
        name: '留园',
        address: '留园路338号',
        rating: 4.8,
        image_url: 'http://store.is.autonavi.com/showpic/liuyuan',
        open_hours: '3月1日-10月31日 07:30-17:30',
      },
    ]

    const previewAssignments = [
      [
        { name: '寒山寺', visit_minutes: 120 },
        { name: '留园', visit_minutes: 150 },
      ],
    ]

    const merged = mergeDayAssignmentsWithSelected(previewAssignments, selected)

    expect(merged[0][0]).toMatchObject({
      name: '寒山寺',
      visit_minutes: 120,
      rating: 4.8,
      image_url: 'http://store.is.autonavi.com/showpic/hanshan',
      open_hours: '08:00-17:00',
      tel: '0512-00000000',
    })
    expect(merged[0][1]).toMatchObject({
      name: '留园',
      visit_minutes: 150,
      image_url: 'http://store.is.autonavi.com/showpic/liuyuan',
      open_hours: '3月1日-10月31日 07:30-17:30',
    })
  })
})

it('allows multi-city rest and travel days without forcing sightseeing', () => {
  const days = [[{ name: '西湖' }], [], [{ name: '雷峰塔' }], []]
  expect(hasUnsupportedEmptyDay(days, true)).toBe(false)
  expect(hasUnsupportedEmptyDay(days, false)).toBe(true)
  expect(hasUnsupportedEmptyDay(days, false, [false, true, false, true])).toBe(false)
})

it('reserves transit days and retains only fitting assignments for the pending catalog',async()=>{
 const {reserveAssignmentWindows}=await import('./dayAssignmentMerge')
 const rows=reserveAssignmentWindows([[{name:'A',visit_minutes:90}],[{name:'B',visit_minutes:90}],[]],[{unavailable:true},{start_minutes:480,end_minutes:600},{unavailable:true}])
 expect(rows[0]).toEqual([]);expect(rows[2]).toEqual([])
 expect(rows[1]).toHaveLength(1)
 expect(reserveAssignmentWindows([[{name:'A'}]],[{unavailable:true}])).toEqual([[]])
})

it('keeps nearby groups together without taking the next group’s entire day',async()=>{
 const {reserveAssignmentWindows}=await import('./dayAssignmentMerge')
 const rows=reserveAssignmentWindows([[{name:'A'},{name:'B'}],[{name:'C'}],[],[],[]],[{unavailable:true},{},{},{},{unavailable:true}])
 expect(rows[1].map(a=>a.name)).toEqual(['A','B'])
 expect(rows[2].map(a=>a.name)).toEqual(['C'])
})
