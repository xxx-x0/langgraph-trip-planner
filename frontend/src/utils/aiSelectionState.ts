import type { DiscoveredAttraction } from '@/types'

export interface AiSelectionSummary {
  mustCount: number
  optionalCount: number
}

export function isCurrentAiSelectionRequest(
  requestId: number,
  currentRequestId: number,
  loading: boolean,
): boolean {
  return loading && requestId === currentRequestId
}

export function applyAiSelectionRecommendations(
  attractions: DiscoveredAttraction[],
  mustIds: Set<string>,
  optionalIds: Set<string>,
  reasons: Record<string, string> = {},
  tags: Record<string, string[]> = {},
): AiSelectionSummary {
  let mustCount = 0
  let optionalCount = 0

  for (const attraction of attractions) {
    attraction.selected = false
    attraction.recommendation = null
    attraction.recommendation_reason = undefined
    attraction.recommendation_tags = undefined

    if (!attraction.poi_id) continue

    if (mustIds.has(attraction.poi_id)) {
      attraction.recommendation = 'must'
      attraction.selected = true
      attraction.recommendation_reason = reasons[attraction.poi_id]
      attraction.recommendation_tags = tags[attraction.poi_id]
      mustCount++
    } else if (optionalIds.has(attraction.poi_id)) {
      attraction.recommendation = 'optional'
      attraction.recommendation_reason = reasons[attraction.poi_id]
      attraction.recommendation_tags = tags[attraction.poi_id]
      optionalCount++
    }
  }

  return { mustCount, optionalCount }
}
