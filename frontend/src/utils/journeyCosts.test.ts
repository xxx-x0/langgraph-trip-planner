import {describe,it,expect} from 'vitest'
import {extraCostLabel} from './journeyCosts'

describe('extra-cost completeness',()=>{
  it('does not present a saved partial zero as free transport extras',()=>{
    expect(extraCostLabel({currency:'CNY',extras_total:0,extra_costs:{taxes:0,baggage:null,transfers:null,overnight:0}})).toBe('尚未核全（已知小计 0 CNY）')
  })
  it('distinguishes unknown costs, partial sums and an explicitly complete zero',()=>{
    expect(extraCostLabel({currency:'CNY',extras_total:null})).toBe('未知')
    expect(extraCostLabel({currency:'CNY',extras_total:99,extra_costs:{taxes:20,baggage:0,transfers:null,overnight:0}})).toBe('尚未核全（已知小计 20 CNY）')
    expect(extraCostLabel({currency:'CNY',extras_total:0,extra_costs:{taxes:0,baggage:0,transfers:0,overnight:0}})).toBe('0 CNY')
  })
})
