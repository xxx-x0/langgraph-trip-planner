import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TabBudget from './TabBudget.vue'

const base = { total_attractions:0, total_hotels:310, total_meals:91, total_transportation:100, total:501, budget_limit:1000 }
const open = (budget:any) => mount(TabBudget,{props:{budget},global:{stubs:{BudgetChart:true}}})
describe('budget completeness',()=>{
  it('shows unknown costs and cannot claim within budget',()=>{
    const wrapper=open({...base,is_complete:false,is_within_budget:null,unknown_cost_items:['拙政园门票']})
    expect(wrapper.get('[role="alert"]').text()).toContain('拙政园门票')
    expect(wrapper.text()).toContain('已知费用预估小计')
    expect(wrapper.text()).toContain('暂不能判断')
    expect(wrapper.text()).not.toContain('超出预算 ¥-')
    expect(wrapper.text()).not.toContain('✅ 在预算范围内')
  })
  it('reports known excess even with missing prices',()=>{
    const wrapper=open({...base,budget_limit:400,is_complete:false,is_within_budget:false})
    expect(wrapper.text()).toContain('已知费用超出预算 ¥101')
  })
  it('supports legacy history without claiming complete prices',()=>{
    const wrapper=open(base)
    expect(wrapper.get('[role="alert"]').text()).toContain('历史预算')
  })
  it('keeps intercity inclusion and the combined transport label consistent',()=>{
    const wrapper=open({...base,total_intercity:341,total_transportation:441,total:842,is_complete:false})
    expect(wrapper.text()).not.toContain('往返大交通尚未纳入')
    expect(wrapper.text()).toContain('往返大交通 341 元，市内交通估算 100 元')
    expect(wrapper.findAll('.budget-item').at(-1)!.text()).toContain('交通费用合计¥441')
  })
  it('reports complete estimate within its limit',()=>{
    const wrapper=open({...base,is_complete:true,is_within_budget:true})
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('✅ 在预算范围内')
  })
})
