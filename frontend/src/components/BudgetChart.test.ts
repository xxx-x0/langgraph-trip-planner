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


it('refreshes chart colors on theme changes and releases the resize observer',async()=>{
 const {useTheme}=await import('@/composables/useTheme');const {nextTick}=await import('vue')
 const disconnect=vi.fn(),observe=vi.fn();vi.stubGlobal('ResizeObserver',class {observe=observe;disconnect=disconnect})
 const w=mount(BudgetChart,{props:{budget:{total_attractions:1,total_hotels:2,total_meals:3,total_transportation:4,total:10}}})
 const theme=useTheme();const before=chart.setOption.mock.calls.at(-1)![0].title.textStyle.color
 theme.toggleTheme();await nextTick()
 expect(chart.setOption.mock.calls.at(-1)![0].title.textStyle.color).not.toBe(before)
 expect(observe).toHaveBeenCalledTimes(1);w.unmount();expect(disconnect).toHaveBeenCalledTimes(1);vi.unstubAllGlobals()
})
