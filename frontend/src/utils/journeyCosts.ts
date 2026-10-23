import type {JourneyLeg} from '@/types'

// A partial extra-cost sum is not the total, even when its known items are zero.
export function extraCostLabel(leg: Pick<JourneyLeg, 'extra_costs' | 'extras_total' | 'currency'>): string {
  if (!leg.extra_costs) return leg.extras_total == null ? '未知' : `${leg.extras_total} ${leg.currency}`
  const amounts = [leg.extra_costs.taxes, leg.extra_costs.baggage, leg.extra_costs.transfers, leg.extra_costs.overnight]
  const known = amounts.filter((n): n is number => n != null)
  if (!known.length) return '未知'
  const sum = Math.round(known.reduce((a, b) => a + b, 0) * 100) / 100
  return known.length === amounts.length ? `${sum} ${leg.currency}` : `尚未核全（已知小计 ${sum} ${leg.currency}）`
}
