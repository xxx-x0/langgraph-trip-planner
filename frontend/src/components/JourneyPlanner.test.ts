import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,expect,it,vi} from 'vitest'
import JourneyPlanner from './JourneyPlanner.vue'
import {collectJourneyTickets} from '@/utils/journeySearch'
import {recommendJourneys} from '@/services/api'
import type {Journey,TripFormData} from '@/types'

vi.mock('@/utils/journeySearch',()=>({collectJourneyTickets:vi.fn()}))
vi.mock('@/services/api',()=>({recommendJourneys:vi.fn()}))
const request:TripFormData={city:'北京',start_date:'2026-11-10',end_date:'2026-11-12',travel_days:3,transportation:'公共交通',accommodation:'酒店',companions:{count:1,type:'solo'},preferences:[],food_preference:'本地特色',free_text_input:''}
const journey:Journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai',planning:{arrival_policy:'unreserved',departure_policy:'unreserved'}}
const leg=(direction:string)=>({mode:'train',service_number:direction==='outbound'?'G1':'G2',departure_time:direction==='outbound'?'2026-11-10T08:00':'2026-11-12T19:00',arrival_time:direction==='outbound'?'2026-11-10T12:00':'2026-11-12T23:00',departure_station:'上海虹桥',arrival_station:'北京南',departure_timezone:'Asia/Shanghai',arrival_timezone:'Asia/Shanghai',passengers:1,booking_status:'planned',price_source:'unknown',ticket_total:null})
const option={id:'journey_0',journey:{...journey,outbound:leg('outbound'),inbound:leg('inbound')},door_minutes:870,reference_fare_per_person:600,days:[{date:'2026-11-10',window:{start_minutes:810,end_minutes:1440}},{date:'2026-11-12',window:{start_minutes:0,end_minutes:1005}}],note:'按班次衔接景点'}
function setup(value:Journey|null=journey){
 let w:any
 w=mount(JourneyPlanner,{props:{request:{...request,journey:value},modelValue:value,'onUpdate:modelValue':(next)=>w.setProps({modelValue:next,request:{...request,journey:next}})}})
 return w
}
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text()===text)!
beforeEach(()=>{vi.clearAllMocks();vi.mocked(collectJourneyTickets).mockResolvedValue({batches:[],notices:['铁路读取 80 条']});vi.mocked(recommendJourneys).mockResolvedValue({options:[option],ranked_by:'jev',message:'已搭配方案'})})

describe('joint journey planning',()=>{
 it('uses mode choices for querying without forcing manual ticket fields or closing days',async()=>{
  const w=setup(null)
  await w.get('input[aria-label="出发城市"]').setValue('上海');await flushPromises()
  await button(w,'只看铁路').trigger('click')
  expect(w.props('modelValue').planning).toMatchObject({arrival_policy:'unreserved',departure_policy:'unreserved'})
  expect(w.props('modelValue').outbound).toBeNull()
  expect(w.get('.manual-journey').attributes('open')).toBeUndefined()
  await button(w,'AI 帮我搭配往返').trigger('click');await flushPromises()
  expect(collectJourneyTickets).toHaveBeenCalledWith(expect.anything(),'train',expect.any(AbortSignal),expect.any(Function))
  expect(w.props('modelValue').outbound).toBeNull()
  expect(w.text()).toContain('13:30—22:00 可安排活动')
  await button(w,'用此方案衔接景点').trigger('click');await flushPromises()
  expect(w.props('modelValue').outbound.service_number).toBe('G1');expect(w.props('modelValue').outbound.ticket_total).toBeNull()
  w.unmount()
 })
 it('plans automatically on Continue and adopts only a returned real proposal',async()=>{
  const w=setup()
  expect(await w.vm.prepare()).toBe(true);await flushPromises()
  expect(w.props('modelValue').outbound.service_number).toBe('G1')
  expect(w.text()).toContain('已按此方案衔接景点')
  expect(await w.vm.prepare()).toBe(true)
  expect(collectJourneyTickets).toHaveBeenCalledTimes(1)
  w.unmount()
 })
 it('keeps scenery planning available after no tickets without making up a schedule',async()=>{
  vi.mocked(recommendJourneys).mockResolvedValue({options:[],ranked_by:'rules',message:'未取得班次，安排暂定'})
  const w=setup()
  expect(await w.vm.prepare()).toBe(true)
  expect(w.props('modelValue')).toEqual(journey)
  expect(await w.vm.prepare()).toBe(true);expect(collectJourneyTickets).toHaveBeenCalledTimes(1)
  w.unmount()
 })
 it('rejects a late recommendation after preferences change',async()=>{
  let finish:any;vi.mocked(recommendJourneys).mockImplementationOnce(()=>new Promise(r=>{finish=r}))
  const w=setup();await button(w,'AI 帮我搭配往返').trigger('click');await flushPromises()
  await button(w,'只看飞机').trigger('click')
  finish({options:[option],ranked_by:'ai',message:'old'});await flushPromises()
  expect(w.find('article').exists()).toBe(false);expect(w.props('modelValue')).toEqual(journey)
  expect(vi.mocked(recommendJourneys).mock.calls[0][1]?.aborted).toBe(true)
  w.unmount()
 })
 it('invalidates generated ticket times when the travel dates change',async()=>{
  const w=setup();await w.vm.prepare();await flushPromises()
  await w.setProps({request:{...request,start_date:'2026-11-11',travel_days:2,journey:w.props('modelValue')}});await flushPromises()
  expect(w.props('modelValue').outbound).toBeNull();expect(w.props('modelValue').inbound).toBeNull()
  w.unmount()
 })
 it('preserves booked tickets and rejects incomplete manual edits before continuing',async()=>{
  const booked=JSON.parse(JSON.stringify(option.journey));booked.outbound.booking_status='booked'
  const w=setup(booked)
  expect(w.get('input[aria-label="出发城市"]').attributes('disabled')).toBeDefined()
  expect(await w.vm.prepare()).toBe(true);expect(collectJourneyTickets).not.toHaveBeenCalled()
  await w.setProps({modelValue:{...journey,outbound:{...leg('outbound'),arrival_time:''}}})
  expect(await w.vm.prepare()).toBe(false)
  expect(w.get('.manual-journey').attributes('open')).toBeDefined()
  w.unmount()
 })
})
