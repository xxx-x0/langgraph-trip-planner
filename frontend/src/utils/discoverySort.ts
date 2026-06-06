import type { DiscoveredAttraction } from '@/types'

function normalizedRating(attraction: DiscoveredAttraction): number {
  return typeof attraction.rating === 'number' && Number.isFinite(attraction.rating)
    ? attraction.rating
    : -1
}

export function sortAttractionsByRating<T extends DiscoveredAttraction>(items: readonly T[]): T[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const ratingDiff = normalizedRating(b.item) - normalizedRating(a.item)
      return ratingDiff || a.index - b.index
    })
    .map(({ item }) => item)
}
