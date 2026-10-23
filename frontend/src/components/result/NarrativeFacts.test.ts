import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TabItinerary from './TabItinerary.vue'
import TabOverview from './TabOverview.vue'

function plan() {
  return {city:'苏州',days:[{date:'2026-10-15',day_index:0,description:'旧说明：已删除景点',attractions:[],meals:[],route_segments:[]}],weather_info:[],overall_suggestions:'旧建议：全部免费'} as any
}
const global={stubs:{'a-collapse':{template:'<div><slot /></div>'},'a-collapse-panel':{template:'<div><slot /></div>'},DayTimeline:true}}

describe('saved explanation rendering',()=>{
  it('suppresses legacy daily and global prose that lacks verified provenance',()=>{
    const tripPlan=plan()
    const day=mount(TabItinerary,{props:{tripPlan,editMode:false,attractionPhotos:{},activeDays:[0]},global})
    const overview=mount(TabOverview,{props:{tripPlan}})
    expect(day.text()).not.toContain('已删除景点')
    expect(day.text()).toContain('旧版说明尚未核对')
    expect(overview.text()).not.toContain('全部免费')
    day.unmount();overview.unmount()
  })
  it('renders updated facts and external names as plain text',()=>{
    const tripPlan=plan()
    Object.assign(tripPlan,{narrative_source:'itinerary_facts_v1',overall_suggestions:'费用待确认：<img src=x onerror=alert(1)>'})
    Object.assign(tripPlan.days[0],{description_source:'itinerary_facts_v1',description:'12:00–13:00 游览：<b>花园</b>'})
    const day=mount(TabItinerary,{props:{tripPlan,editMode:false,attractionPhotos:{},activeDays:[0]},global})
    const overview=mount(TabOverview,{props:{tripPlan}})
    expect(day.text()).toContain('12:00–13:00 游览：<b>花园</b>')
    expect(day.find('.info-card-value b').exists()).toBe(false)
    expect(overview.text()).toContain('<img')
    expect(overview.find('img').exists()).toBe(false)
    day.unmount();overview.unmount()
  })
})
