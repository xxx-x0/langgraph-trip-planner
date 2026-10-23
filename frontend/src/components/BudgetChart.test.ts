import {mount} from '@vue/test-utils'
import {it,expect,vi} from 'vitest'
import BudgetChart from './BudgetChart.vue'
const chart=vi.hoisted(()=>({setOption:vi.fn(),dispose:vi.fn(),resize:vi.fn()}))
vi.mock('echarts',()=>({init:()=>chart,graphic:{LinearGradient:class {}}}))
it('charts known estimates without inventing category budgets from the total limit',()=>{
 const wrapper=mount(BudgetChart,{props:{budget:{total_attractions:0,total_hotels:196,total_meals:358,total_transportation:2600,total:3154,budget_limit:5000,is_complete:false}}})
 const option=chart.setOption.mock.calls[0]![0]
 expect(option.series).toHaveLength(1)
 expect(option.series[0].name).toBe('已知费用预估')
 expect(option.series[0].data.map((d:any)=>d.value)).toEqual([0,196,358,2600])
 expect(JSON.stringify(option)).not.toContain('预算参考')
 expect(JSON.stringify(option)).not.toContain('实际费用')
 wrapper.unmount()
})
