import { describe, expect, it } from 'vitest'
import type { DiscoveredAttraction } from '@/types'
import { sortAttractionsByRating } from './discoverySort'

const attraction = (name: string, rating?: number): DiscoveredAttraction => ({
  name,
  description: '',
  address: '',
  category: '景点',
  rating,
})

describe('sortAttractionsByRating', () => {
  it('puts higher rated attractions first and keeps unrated attractions last', () => {
    const input = [
      attraction('无评分'),
      attraction('低评分', 3.9),
      attraction('高评分', 4.8),
      attraction('中评分', 4.5),
    ]

    const result = sortAttractionsByRating(input)

    expect(result.map(a => a.name)).toEqual(['高评分', '中评分', '低评分', '无评分'])
  })

  it('keeps original order when ratings are equal or missing', () => {
    const input = [
      attraction('第一个同分', 4.7),
      attraction('第二个同分', 4.7),
      attraction('第一个无评分'),
      attraction('第二个无评分'),
    ]

    const result = sortAttractionsByRating(input)

    expect(result.map(a => a.name)).toEqual([
      '第一个同分',
      '第二个同分',
      '第一个无评分',
      '第二个无评分',
    ])
  })
})
