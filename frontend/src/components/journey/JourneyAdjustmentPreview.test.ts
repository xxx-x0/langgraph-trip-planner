import {mount} from '@vue/test-utils'
import {expect,it} from 'vitest'
import JourneyAdjustmentPreview from './JourneyAdjustmentPreview.vue'

const days=[{date:'2026-11-08',attractions:[{name:'公园'}]},{date:'2026-11-09',attractions:[{name:'博物馆'}]}]
const leg:any={mode:'train',service_number:'G1',departure_time:'2026-11-08T07:11',arrival_time:'2026-11-08T09:29',departure_station:'杭州东',arrival_station:'温州南',passengers:2,ticket_total:null,currency:'CNY',booking_status:'planned'}
const journey={origin_city:'杭州',return_city:'杭州',destination_timezone:'Asia/Shanghai',outbound:leg,inbound:null}
const preview={adjustment_id:'verified',changes:['2026-11-08：按交通窗口核对原选景点、用餐和实际路线','2026-11-08：移除本城用餐 原餐厅；请核对在途或其他日期的用餐','公园移至2026-11-09，保留原游览时长'],
  days_detail:[{date:days[0].date,attractions:[],timeline_schedule:[]},{date:days[1].date,attractions:[{name:'公园'}],timeline_schedule:[{kind:'attraction',ref_name:'公园',start_time:'09:00',end_time:'10:30'}]}],
  impacts:[{date:days[0].date,window:{start_minutes:659,end_minutes:1440},changes:[],conflicts:[]},{date:days[1].date,window:{start_minutes:0,end_minutes:832},changes:[],conflicts:[]}],unassigned_attractions:[{name:'博物馆'}],intercity_total:0,budget:{total:533,is_complete:false}}

it('keeps moved, cancelled and pending activities visible while collapsing routine audit text',()=>{
  const w=mount(JourneyAdjustmentPreview,{props:{preview,journey,days,originalDetails:[null,null],acknowledged:false,disabled:false}})
  const main=w.get('[aria-label="需要核对的调整"]')
  expect(main.text()).toContain('公园');expect(main.text()).toContain('跨日移动')
  expect(main.text()).toContain('原餐厅未能匹配合适时段')
  expect(main.text()).toContain('博物馆');expect(main.text()).toContain('待安排清单')
  expect(main.text()).not.toContain('按交通窗口核对原选景点')
  expect(w.get('.proposal-evidence').attributes('open')).toBeUndefined()
  expect(w.get('.proposal-evidence').text()).toContain('移除本城用餐 原餐厅')
  expect(w.get('.ticket-card').text()).toContain('票价待核对')
  expect(w.text()).not.toContain('¥0');expect(w.text()).toContain('¥533 · 尚未核齐')
  w.unmount()
})

it('shows a chosen day timeline without treating an unassembled day as verified',async()=>{
  const data={...preview,days_detail:[null,preview.days_detail[1]]}
  const w=mount(JourneyAdjustmentPreview,{props:{preview:data,journey,days,originalDetails:[null,null],acknowledged:false,disabled:false}})
  expect(w.find('.proposal-timeline').exists()).toBe(false)
  await w.get('[aria-label="查看2026-11-09的时间安排"]').trigger('click')
  expect(w.get('.proposal-timeline').text()).toContain('09:00');expect(w.get('.proposal-timeline').text()).toContain('公园')
  await w.get('[aria-label="查看2026-11-08的时间安排"]').trigger('click')
  expect(w.get('.proposal-timeline').text()).toContain('当天尚未生成日程')
  expect(w.find('.proposal-timeline ol').exists()).toBe(false)
  expect(w.get('.primary-action').attributes('disabled')).toBeDefined()
  w.unmount()
})

it('keeps unresolved conflicts outside the disclosure and emits only the explicit action',async()=>{
  const data={...preview,impacts:[{...preview.impacts[0],conflicts:['固定预约超出抵达后的窗口']}]}
  const w=mount(JourneyAdjustmentPreview,{props:{preview:data,journey,days,originalDetails:[null,null],acknowledged:false,disabled:false}})
  expect(w.get('[role="alert"]').text()).toContain('固定预约超出抵达后的窗口')
  expect(w.get('[role="alert"]').element.closest('details')).toBeNull()
  await w.get('.proposal-ack input').setValue(true)
  expect(w.emitted('acknowledge')).toEqual([[true]])
  expect(w.emitted('save')).toBeUndefined()
  await w.get('.secondary-action').trigger('click')
  expect(w.emitted('cancel')).toEqual([[]]);expect(w.emitted('save')).toBeUndefined()
  w.unmount()
})

it('shows restored restaurant and unresolved meal separately without claiming both succeeded',()=>{
  const data={...preview,changes:['2026-11-08：重新推荐晚餐：新店'],meal_recovery:[
    {date:days[0].date,slot:'dinner',status:'scheduled',restaurant:'南塘附近餐厅',old_restaurant:'原店',start_time:'19:40',end_time:'20:40',selection_method:'ai',reason:'已核对实际市内路线',cautions:['人均价格未提供']},
    {date:days[1].date,slot:'dinner',status:'unavailable',reason:'当前交通窗口没有完整的60分钟用餐时段'}]}
  const w=mount(JourneyAdjustmentPreview,{props:{preview:data,journey,days,originalDetails:[null,null],acknowledged:false,disabled:false}})
  const meals=w.get('[aria-label="重新推荐的用餐"]')
  expect(meals.text()).toContain('南塘附近餐厅');expect(meals.text()).toContain('19:40—20:40')
  expect(meals.text()).toContain('AI 选店');expect(meals.text()).toContain('尚未排入')
  expect(meals.text()).not.toContain('请自行')
  expect(w.find('.proposal-changes').text()).not.toContain('重新推荐晚餐：新店')
  expect(w.get('.proposal-buttons .primary-action').attributes('disabled')).toBeDefined()
  w.unmount()
})

it('puts coordinated pace, real breaks and additional return margin before the detailed changes',()=>{
  const data={...preview,coordination:{days:[
    {date:days[0].date,start_time:'10:46',end_time:'19:29',visit_minutes:240,rest_minutes:30,meal_count:2,return_margin_minutes:null},
    {date:days[1].date,start_time:'08:00',end_time:'18:00',visit_minutes:270,rest_minutes:30,meal_count:2,return_margin_minutes:33}]}}
  const w=mount(JourneyAdjustmentPreview,{props:{preview:data,journey,days,originalDetails:[null,null],acknowledged:false,disabled:false}})
  const pace=w.get('[aria-label="调整后的旅行节奏"]')
  expect(w.get('h3').text()).toBe('看看整趟的新安排')
  expect(pace.text()).toContain('10:46—19:29');expect(pace.text()).toContain('08:00—18:00')
  expect(pace.text()).toContain('休息 30 分钟');expect(pace.text()).toContain('接驳外余量 33 分钟')
  expect(pace.text()).toContain('游玩 4小时30分钟');expect(pace.text()).toContain('1 个景点暂留待安排')
  expect(pace.element.closest('details')).toBeNull()
  expect(w.get('.primary-action').attributes('disabled')).toBeDefined()
  w.unmount()
})
