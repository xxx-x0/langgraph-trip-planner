import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DayTimeline from './DayTimeline.vue'

describe('persisted service schedule',()=>{
  it('uses exact saved waits and five-minute routes without recomputing meal timing',()=>{
    const wrapper=mount(DayTimeline,{props:{day:{date:'2026-10-14',day_index:0,description:'',transportation:'公共交通',accommodation:'',
      attractions:[],meals:[],route_segments:[],day_start_time:'08:00',timeline_schedule:[
        {kind:'wait',ref_name:'等待用餐时段',start_time:'10:00',end_time:'11:30',start_minutes:600,end_minutes:690,duration:90},
        {kind:'travel',ref_name:'A → 餐厅',start_time:'11:30',end_time:'11:35',start_minutes:690,end_minutes:695,duration:5,mode:'步行'},
        {kind:'meal',ref_name:'真实餐厅',start_time:'11:35',end_time:'12:35',start_minutes:695,end_minutes:755,duration:60,detail:'午餐'},
      ]}}})
    expect(wrapper.text()).toContain('10:00 - 12:35')
    expect(wrapper.text()).toContain('5分钟')
    expect(wrapper.text()).toContain('11:35')
    expect(wrapper.text()).toContain('午餐')
    expect(wrapper.text()).toContain('等待用餐时段')
  })
})

it('renders reserved rest with its saved times and explanation',()=>{
  const wrapper=mount(DayTimeline,{props:{day:{date:'2026-10-28',day_index:2,description:'',transportation:'公共交通',accommodation:'',attractions:[],meals:[],route_segments:[],timeline_schedule:[{kind:'rest',ref_name:'下午歇一歇',start_time:'14:00',end_time:'17:00',start_minutes:840,end_minutes:1020,duration:180,detail:'在当前区域自行休息'}]}}})
  expect(wrapper.text()).toContain('14:00 - 17:00');expect(wrapper.text()).toContain('下午歇一歇');expect(wrapper.text()).toContain('在当前区域自行休息')
})
