import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HotelCard from './HotelCard.vue'

const quote = { source:'aigohotel', cost_kind:'query_quote', status:'detail_returned', amount:123.45,
 currency:'CNY', unit:'average_per_room_night', check_in:'2026-10-19',check_out:'2026-10-21', nights:2,
 occupancy:{room_count:1,adults_per_room:2,children_ages:[8]}, occupancy_confirmed:true,
 queried_at:'2026-10-15T11:00:00Z',unsupported_conditions:[],room_name:'家庭房',bed_type:'双床',
 meal_plan:'不含早餐',cancellation_policy:'不可退',taxes_included:null,availability:'returned' }
const open=(q:any)=>mount(HotelCard,{props:{hotel:{name:'H',address:'苏州',type:'酒店',price:800,original_price:1000,estimated_cost:800,quote:q} as any}})
describe('hotel quote conditions',()=>{
 it('shows quote conditions and fractional price without invented discounts',()=>{
  const w=open(quote)
  for(const text of ['查询参考报价','123.45','整段均价','2 晚','儿童 8 岁','不含早餐','税费待确认','不可退','尚未预订','AIGoHotel']) expect(w.text()).toContain(text)
  expect(w.text()).not.toContain('省¥')
 })
 it('does not display historic estimate as current nightly rate',()=>{
  const w=open(null);expect(w.text()).toContain('当前房型价格待确认');expect(w.text()).not.toContain('800')
 })
 it('shows unsupported multi-room units and keeps foreign currency',()=>{
  const w=open({...quote,currency:'USD',unit:'unknown',unsupported_conditions:['多房报价口径待确认']})
  expect(w.text()).toContain('USD 123.45');expect(w.text()).not.toContain('¥')
  expect(w.get('[role="alert"]').text()).toContain('多房报价口径待确认')
 })
 it('keeps missing rate unknown and zero price explicit',()=>{
  expect(open({...quote,amount:null}).text()).toContain('房型价格待确认')
  expect(open({...quote,amount:0}).text()).toContain('0.00')
 })
})
