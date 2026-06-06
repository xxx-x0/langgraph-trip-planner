import { describe, expect, it } from 'vitest'
import type { DiscoveredAttraction } from '@/types'
import {
  applyAiSelectionRecommendations,
  isCurrentAiSelectionRequest,
} from './aiSelectionState'

const attraction = (
  name: string,
  poiId: string,
  selected = false,
): DiscoveredAttraction => ({
  name,
  poi_id: poiId,
  description: '',
  address: '',
  category: '景点',
  selected,
})

describe('aiSelectionState', () => {
  it('ignores stale AI selection responses', () => {
    expect(isCurrentAiSelectionRequest(1, 2, true)).toBe(false)
    expect(isCurrentAiSelectionRequest(2, 2, false)).toBe(false)
    expect(isCurrentAiSelectionRequest(2, 2, true)).toBe(true)
  })

  it('replaces manual selections with the latest AI must picks and marks optional picks', () => {
    const attractions = [
      attraction('故宫博物院', 'poi-1', true),
      attraction('天坛公园', 'poi-2', false),
      attraction('景山公园', 'poi-3', true),
    ]

    const summary = applyAiSelectionRecommendations(
      attractions,
      new Set(['poi-2']),
      new Set(['poi-3']),
      {
        'poi-2': '符合你的历史文化偏好',
        'poi-3': '时间充裕时可顺路游览',
      },
      {
        'poi-2': ['历史文化', '经典必去'],
        'poi-3': ['备选'],
      },
    )

    expect(summary).toEqual({ mustCount: 1, optionalCount: 1 })
    expect(attractions.map(a => ({
      name: a.name,
      selected: a.selected,
      recommendation: a.recommendation,
      recommendation_reason: a.recommendation_reason,
      recommendation_tags: a.recommendation_tags,
    }))).toEqual([
      {
        name: '故宫博物院',
        selected: false,
        recommendation: null,
        recommendation_reason: undefined,
        recommendation_tags: undefined,
      },
      {
        name: '天坛公园',
        selected: true,
        recommendation: 'must',
        recommendation_reason: '符合你的历史文化偏好',
        recommendation_tags: ['历史文化', '经典必去'],
      },
      {
        name: '景山公园',
        selected: false,
        recommendation: 'optional',
        recommendation_reason: '时间充裕时可顺路游览',
        recommendation_tags: ['备选'],
      },
    ])
  })
})
