import { mount,flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TabOverview from './TabOverview.vue'
import Antd from 'ant-design-vue'
import TabItinerary from './TabItinerary.vue'
import JourneySummary from '../JourneySummary.vue'

const plan = { city: '青岛', days: [
  { date: '2026-10-30', attractions: [{ name: '信号山公园' }], meals: [], pending_confirmations: ['门票待核对'] },
  { date: '2026-10-31', attractions: [], meals: [], pending_confirmations: ['门票待核对', '返程接驳待核对'] },
], narrative_source: 'itinerary_facts_v1', overall_suggestions: '保存的完整说明' } as any

describe('saved trip reading', () => {
  it('distinguishes a cross-midnight arrival travel day from the absence of a new hotel night', () => {
    const saved = { ...plan, days: [
      { date: '2026-10-28', attractions: [], meals: [], overnight_stay: false, accommodation: '酒店', travel_window: { day_role: 'travel' } },
      { date: '2026-10-30', attractions: [], meals: [], overnight_stay: false, hotel: { name: '已存酒店位置' } },
    ] } as any
    const before = JSON.stringify(saved)
    const wrapper = mount(TabOverview, { props: { tripPlan: saved } })
    const cards = wrapper.findAll('.day-card')
    expect(cards[0].text()).toContain('本日留给交通与抵离')
    expect(cards[0].text()).toContain('交通日')
    expect(cards[0].find('.day-stay').text()).toBe('在途用餐与住宿待核对')
    expect(cards[1].text()).toContain('不计新增住宿')
    expect(cards[1].text()).toContain('已存酒店位置')
    expect(wrapper.text()).not.toContain('离开日')
    expect(JSON.stringify(saved)).toBe(before)
    wrapper.unmount()
  })
  it('opens the chosen day and deduplicates pending confirmations without hiding their meaning', async () => {
    const wrapper = mount(TabOverview, { props: { tripPlan: plan } })
    await wrapper.findAll('.day-card')[1].trigger('click')
    expect(wrapper.emitted('openDay')).toEqual([[1]])
    expect(wrapper.text()).toContain('还有 2 项待确认')
    expect(wrapper.find('.day-card:last-child').text()).toContain('当天尚未安排景点')
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    await wrapper.setProps({ expanded: true })
    expect(wrapper.find('details').attributes('open')).toBeDefined()
    expect(wrapper.text()).toContain('保存的完整说明')
  })
  it('keeps party totals and unknown extras distinct while source details remain available for export', async () => {
    const journey = { origin_city: '杭州', return_city: '杭州', destination_timezone: 'Asia/Shanghai', outbound: {
      service_number: 'SC4766', departure_time: '2026-10-30T10:05', arrival_time: '2026-10-30T11:50',
      departure_timezone: 'Asia/Shanghai', arrival_timezone: 'Asia/Shanghai', passengers: 2,
      ticket_total: 1140, currency: 'CNY', price_source: 'user_quote', price_note: '双人含税报价',
      extra_costs: { taxes: 0, baggage: null, transfers: null, overnight: 0 },
    } } as any
    const wrapper = mount(JourneySummary, { props: { journey, city: '青岛', days: [{ date: '2026-10-30' }] } })
    expect(wrapper.find('.leg-price').text()).toContain('全体 2 人票价1140')
    expect(wrapper.find('.leg-extra').text()).toContain('尚未核全')
    expect(wrapper.text()).toContain('需重新核价')
    expect(wrapper.text()).toContain('尚未核对')
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    await wrapper.setProps({ expanded: true })
    expect(wrapper.findAll('details').every(detail => detail.attributes('open') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('双人含税报价')
  })
})


it('expands every saved day for export and restores the selected day without mutating saved facts',async()=>{
 const saved={...plan,days:plan.days.map((d:any,i:number)=>({...d,day_index:i,description:'事实说明',description_source:'itinerary_facts_v1',transportation:'步行',accommodation:'待确认',route_segments:[]}))}
 const before=JSON.stringify(saved)
 const w=mount(TabItinerary,{props:{tripPlan:saved,editMode:false,expanded:false,activeDays:[1],attractionPhotos:{}},global:{plugins:[Antd],stubs:{AttractionCard:true,DayTimeline:true}}})
 await flushPromises()
 expect(w.findAll('.ant-collapse-header[aria-expanded=true]').map(t=>t.text())).toEqual([expect.stringContaining('第2天')])
 await w.setProps({expanded:true});await flushPromises()
 expect(w.findAll('.ant-collapse-header[aria-expanded=true]')).toHaveLength(2)
 await w.setProps({expanded:false});await flushPromises()
 expect(w.findAll('.ant-collapse-header[aria-expanded=true]').map(t=>t.text())).toEqual([expect.stringContaining('第2天')])
 await w.findAll('.ant-collapse-header')[0].trigger('click');await flushPromises()
 expect(w.emitted('update:activeDays')?.at(-1)).toEqual([[0]])
 expect(JSON.stringify(saved)).toBe(before);w.unmount()
})
