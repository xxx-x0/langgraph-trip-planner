import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import MultiTripItinerary from './MultiTripItinerary.vue'
const windowFor=(date:string)=>({date,start_minutes:540,end_minutes:1200,available_minutes:660,rest_periods:[]})
const cities=[
  {id:'s',city:'苏州',nights:2,source_draft:'draft_s',windows:[windowFor('2026-10-20'),windowFor('2026-10-21')],days:[{date:'2026-10-21',timeline_schedule:[{kind:'meal',start_time:'12:00',end_time:'13:00',ref_name:'第二天午餐'}]},{date:'2026-10-20',timeline_schedule:[{kind:'attraction',start_time:'09:00',end_time:'11:00',ref_name:'第一天景点'}]}]},
  {id:'h',city:'杭州',nights:3,source_draft:null,windows:[windowFor('2026-10-22')],days:[]},
]
const mountView=(extra={})=>mount(MultiTripItinerary,{props:{cities,readonly:false,disabled:false,...extra}})
describe('multi-city daily overview',()=>{
  it('keeps the shared travel date when switching its two cities and targets its exact transport',async()=>{
    const data=[cities[0],{...cities[1],windows:[windowFor('2026-10-21'),windowFor('2026-10-22')]}]
    const w=mountView({cities:data,transfers:[{from_stop:'s',to_stop:'h',from_city:'苏州',to_city:'杭州',leg:{service_number:'G1',departure_time:'2026-10-21T15:00',arrival_time:'2026-10-21T16:00'}}]})
    expect(w.findAll('.journey-days button')).toHaveLength(3)
    await w.findAll('.journey-days button')[1]!.trigger('click')
    await w.findAll('.day-transfer-actions button')[1]!.trigger('click')
    await w.setProps({focusCity:'h'})
    expect(w.get('.city-title').text()).toContain('杭州')
    expect(w.get('.day-heading').text()).toContain('2026-10-21')
    await w.get('.day-transfer-actions button').trigger('click')
    expect(w.emitted('transport')).toEqual([['s','h']])
    w.unmount()
  })
  it('shows stored route details as text instead of generic instructions',async()=>{
    const w=mountView({cities:[{...cities[0],days:[{date:'2026-10-20',timeline_schedule:[{kind:'travel',start_time:'09:00',end_time:'10:00',ref_name:'码头路线',detail:'乘坐轮渡 <script>bad</script>'}]}]}]})
    await w.get('.day-lens button').trigger('click');await w.get('.activity-open').trigger('click')
    expect(w.get('.activity-detail').text()).toContain('乘坐轮渡 <script>bad</script>')
    expect(w.find('script').exists()).toBe(false);w.unmount()
  })
  it('returns directly to the edited city and points provisional days to transport',async()=>{
    const w=mountView({focusCity:'h',cities:[cities[0],{...cities[1],windows:[{...cities[1].windows[0],provisional:true}]}]})
    expect(w.get('.city-title').text()).toContain('杭州')
    await w.get('.transport-shortcut').trigger('click')
    expect(w.emitted('transport')).toHaveLength(1)
    await w.setProps({readonly:true})
    expect(w.find('.transport-shortcut').exists()).toBe(false)
    w.unmount()
  })
  it('matches saved days by date and keeps city/day selection separate',async()=>{
    const w=mountView();expect(w.text()).toContain('第一天景点');expect(w.text()).not.toContain('第二天午餐')
    await w.get('.day-picker button:nth-child(2)').trigger('click');expect(w.text()).toContain('第二天午餐');expect(w.text()).not.toContain('第一天景点')
    await w.get('.city-list button:nth-of-type(2)').trigger('click');expect(w.text()).toContain('2026-10-22');expect(w.text()).not.toContain('第二天午餐');expect(w.text()).toContain('还没有同步每日安排')
    await w.get('.city-actions button').trigger('click');expect(w.emitted('plan')).toEqual([['h']]);w.unmount()
  })
  it('does not offer editing a saved version or mutate a dirty draft',async()=>{
    const w=mountView({readonly:true});expect(w.find('.city-actions').exists()).toBe(false)
    await w.setProps({readonly:false,disabled:true});expect(w.findAll('.city-actions button').every(b=>b.attributes('disabled')!==undefined)).toBe(true);w.unmount()
  })
  it('falls back when a selected city is removed and renders external names as text',async()=>{
    const w=mountView();await w.get('.city-list button:nth-of-type(2)').trigger('click')
    await w.setProps({cities:[{...cities[0],city:'<img src=x onerror=alert(1)>'}]})
    expect(w.find('img').exists()).toBe(false);expect(w.text()).toContain('<img src=x onerror=alert(1)>');expect(w.text()).toContain('第一天景点');w.unmount()
  })
  it('keeps every saved time and reveals a collapsed route when its rhythm segment is selected',async()=>{
    const items=[{kind:'travel',start_time:'08:00',end_time:'09:00',ref_name:'去园林的路上'},{kind:'attraction',start_time:'09:00',end_time:'11:00',ref_name:'园林游览'},{kind:'meal',start_time:'11:00',end_time:'12:00',ref_name:'当天午餐'}]
    const data=[{...cities[0],days:[{date:'2026-10-20',timeline_schedule:items}]}]
    const original=JSON.stringify(data)
    const w=mountView({cities:data})
    expect(w.findAll('.timeline li')).toHaveLength(2)
    expect(w.get('.connection-hint').text()).toContain('1 段')
    expect(w.findAll('.rhythm-track button')).toHaveLength(3)
    await w.get('.rhythm-track button').trigger('click')
    expect(w.findAll('.timeline li')).toHaveLength(3)
    expect(w.get('.timeline .highlighted').text()).toContain('去园林的路上')
    expect(w.get('.day-lens button').attributes('aria-pressed')).toBe('true')
    await w.get('.day-lens button').trigger('click')
    expect(w.findAll('.timeline li')).toHaveLength(2)
    expect(JSON.stringify(data)).toBe(original)
    expect(w.emitted('edit')).toBeUndefined()
    w.unmount()
  })
  it('changes a chapter from the cover without carrying the previous activity highlight',async()=>{
    const w=mountView()
    await w.get('.rhythm-track button').trigger('click')
    expect(w.find('.timeline .highlighted').exists()).toBe(true)
    await w.setProps({focusCity:'h'})
    expect(w.get('.city-title').text()).toContain('杭州')
    expect(w.find('.timeline .highlighted').exists()).toBe(false)
    expect(w.find('.day-rhythm').exists()).toBe(false)
    w.unmount()
  })

})
