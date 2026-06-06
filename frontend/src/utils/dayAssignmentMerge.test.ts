import { describe, expect, it } from 'vitest'
import { mergeDayAssignmentsWithSelected } from './dayAssignmentMerge'

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
