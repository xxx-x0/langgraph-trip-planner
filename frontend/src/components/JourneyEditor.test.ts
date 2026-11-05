import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import JourneyEditor from './JourneyEditor.vue'
import JourneySummary from './JourneySummary.vue'

const button=(w:any,name:string)=>w.findAll('button').find((b:any)=>b.text()===name)!
const latest=(w:any)=>w.emitted('update:modelValue')!.at(-1)![0] as any

describe('manual intercity inputs',()=>{
 it('keeps unknown first and last days adjustable and allows an explicit time boundary',async()=>{
  const w=mount(JourneyEditor,{props:{startDate:'2026-11-10',endDate:'2026-11-14'}})
  await w.get('[aria-label="出发城市"]').setValue('上海')
  expect(latest(w).planning).toMatchObject({arrival_policy:'unreserved',departure_policy:'unreserved',ready_at:null})
  expect(latest(w).outbound).toBeUndefined();expect(w.text()).toContain('首末天不会自动整天留空')
  const select=w.findAll('select').find(s=>s.text().includes('填写预计目的地可用时间'))!
  await select.setValue('time_window');expect(await (w.vm as any).validate()).toBe(false)
  await w.get('input[type="datetime-local"]').setValue('2026-11-10T15:00')
  expect(await (w.vm as any).validate()).toBe(true);expect(latest(w).planning.ready_at).toBe('2026-11-10T15:00')
 })
 it('leaves an old journey without reservations unchanged until the user chooses one',async()=>{
  const old={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
  const w=mount(JourneyEditor,{props:{modelValue:old}})
  expect(w.emitted('update:modelValue')).toBeUndefined()
  const select=w.findAll('select').find(s=>s.text().includes('填写预计目的地可用时间'))!
  expect(select.element.value).toBe('unreserved')
  await select.setValue('travel_day');expect(latest(w).planning).toMatchObject({arrival_policy:'travel_day',departure_policy:'unreserved'})
 })
 it('exposes departure city and modes without opt-in; never invents times or fares',async()=>{
  const w=mount(JourneyEditor,{props:{startDate:'2026-10-30',endDate:'2026-11-05',passengers:2,destinationCity:'青岛'}})
  expect(w.find('input[aria-label="出发城市"]').exists()).toBe(true)
  expect(w.find('input[type=checkbox]').exists()).toBe(false)
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  expect(latest(w)).toMatchObject({origin_city:'杭州',return_city:'杭州'})
  await button(w,'铁路').trigger('click')
  expect(latest(w).outbound).toMatchObject({passengers:2,ticket_total:null,extras_total:null,price_source:'unknown',departure_time:'',arrival_time:''})
  expect(w.text()).toContain('不是地图查询')
  expect(w.text()).toContain('不会下单或改签')
 })
 it('keeps two directions independent and removes hidden fare when postponing a leg',async()=>{
  const w=mount(JourneyEditor)
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  await button(w,'铁路').trigger('click')
  await w.findAll('.leg-tabs button')[1].trigger('click')
  await button(w,'飞机').trigger('click')
  expect(latest(w).outbound.mode).toBe('train')
  expect(latest(w).inbound.mode).toBe('flight')
  await button(w,'稍后确定').trigger('click')
  expect(latest(w).inbound).toBeNull()
  expect(latest(w).outbound.mode).toBe('train')
  await w.findAll('.leg-tabs button')[0].trigger('click')
  await button(w,'稍后确定').trigger('click')
  await w.find('input[aria-label="出发城市"]').setValue('')
  expect(latest(w)).toBeNull()
 })
 it('resets stale ticket facts on mode change but preserves custom buffers',async()=>{
  const w=mount(JourneyEditor)
  await button(w,'铁路').trigger('click')
  const journey=latest(w)
  journey.outbound.ticket_total=400;journey.outbound.service_number='G1';journey.outbound.transfer_before_minutes=105
  await w.setProps({modelValue:journey})
  await button(w,'飞机').trigger('click')
  expect(latest(w).outbound).toMatchObject({mode:'flight',ticket_total:null,service_number:'',transfer_before_minutes:105,departure_time:''})
 })
 it('single-leg editing offers modes immediately and clears externally reset values',async()=>{
  const w=mount(JourneyEditor,{props:{singleLeg:true}})
  expect(w.find('.leg-tabs').exists()).toBe(false)
  await button(w,'铁路').trigger('click')
  await w.setProps({modelValue:latest(w)})
  await w.setProps({modelValue:null})
  expect(w.find('input[type=datetime-local]').exists()).toBe(false)
 })
 it('shows old journeys as provisional, never free or booked',()=>{
  const w=mount(JourneySummary,{props:{city:'苏州'}})
  expect(w.text()).toContain('首末日时间暂定')
  expect(w.text()).toContain('往返费用尚未计入')
  expect(w.findAll('button')).toHaveLength(0)
 })
 it('opens the incomplete return leg and gives a readable price-source error',async()=>{
  const w=mount(JourneyEditor,{props:{passengers:2}})
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  await w.findAll('.leg-tabs button')[1].trigger('click')
  await button(w,'飞机').trigger('click')
  await w.findAll('.leg-tabs button')[0].trigger('click')
  expect(await (w.vm as any).validate()).toBe(false)
  expect(w.find('.leg-tabs button[aria-pressed="true"]').text()).toContain('返程')
  expect(w.find('[role="alert"]').text()).toContain('请补充返程')
  const journey=latest(w)
  Object.assign(journey.inbound,{departure_station:'青岛胶东',arrival_station:'杭州萧山',departure_time:'2026-10-31T18:00',arrival_time:'2026-10-31T20:00',ticket_total:1200})
  await w.setProps({modelValue:journey})
  expect(await (w.vm as any).validate()).toBe(false)
  expect(w.find('[role="alert"]').text()).toContain('价格来源')
  expect(w.find('.price-details').attributes('open')).toBeDefined()
  journey.inbound.price_source='user_estimate'
  await w.setProps({modelValue:JSON.parse(JSON.stringify(journey))})
  expect(await (w.vm as any).validate()).toBe(true)
 })

})
