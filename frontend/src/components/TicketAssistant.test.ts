import {mount,flushPromises} from '@vue/test-utils'
import {describe,it,expect,vi,afterEach} from 'vitest'
import TicketAssistant from './TicketAssistant.vue'
const request:any={city:'北京',start_date:'2026-10-20',end_date:'2026-10-22',companions:{count:2},journey:{origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai',outbound:{booking_status:'booked'}}}
const sample='2026-10-20 上海虹桥 → 北京南 G8 08:00—12:26 二等座 每人661元'
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text().includes(text))!
const field=(w:any,text:string)=>w.findAll('label').find((l:any)=>l.text().startsWith(text))!.find('input,select,textarea')
afterEach(()=>vi.unstubAllGlobals())
async function preview(){const w=mount(TicketAssistant,{props:{request}});await field(w,'车票文字').setValue(sample);await button(w,'识别并预览').trigger('click');await flushPromises();return w}
describe('query and ticket handoff',()=>{
 it('changes the link and copy text for return dates and cities',async()=>{const w=mount(TicketAssistant,{props:{request}});await field(w,'查询方向').setValue('inbound');await field(w,'查询出发日期').setValue('2026-10-23');expect(w.get('a[target="_blank"]').attributes('href')).toContain('date=2026-10-23');expect((w.get('textarea[aria-label="查询条件"]').element as HTMLTextAreaElement).value).toContain('出发地：北京');w.unmount()})
 it('uses saved travel modes and passes only a confirmed all-adult party',async()=>{
  const r:any={...request,hotel_occupancy:{room_count:1,adults_per_room:2,children_ages:[]},journey:{...request.journey,outbound:{mode:'flight'},inbound:{mode:'train'}}}
  const w=mount(TicketAssistant,{props:{request:r}})
  expect(field(w,'查询交通方式').element.value).toBe('flight')
  expect(new URL(w.get('a[target="_blank"]').attributes('href')!).searchParams.get('adult')).toBe('2')
  await field(w,'查询方向').setValue('inbound');expect(field(w,'查询交通方式').element.value).toBe('train')
  await field(w,'查询方向').setValue('outbound');await field(w,'查询同行人数').setValue(3)
  expect(new URL(w.get('a[target="_blank"]').attributes('href')!).searchParams.get('adult')).toBe('1')
  await w.setProps({request:{...r,hotel_occupancy:{room_count:1,adults_per_room:2,children_ages:[8]}}})
  expect(w.text()).toContain('同行票种未明确');w.unmount()
 })
 it('copies only query conditions and reports clipboard failure',async()=>{const writeText=vi.fn().mockResolvedValue(undefined);vi.stubGlobal('navigator',{clipboard:{writeText}});const w=mount(TicketAssistant,{props:{request}});await button(w,'复制查询').trigger('click');await flushPromises();expect(writeText.mock.calls[0][0]).toContain('2026-10-20');expect(writeText.mock.calls[0][0]).not.toContain('booked');writeText.mockRejectedValue(new Error());await button(w,'复制查询').trigger('click');await flushPromises();expect(w.text()).toContain('未能访问剪贴板');w.unmount()})
 it('requires explicit review, clears raw text and adds only a new candidate',async()=>{const w=await preview();expect(button(w,'确认这段车票').attributes('disabled')).toBeDefined();await w.get('.ticket-preview .confirm input[type=checkbox]').setValue(true);await button(w,'确认这段车票').trigger('click');await flushPromises();expect(field(w,'车票文字').element.value).toBe('');expect(w.emitted('add')).toBeUndefined();await button(w,'作为新备选').trigger('click');const c=w.emitted('add')![0][0] as any;expect(c.journey.outbound.ticket_total).toBe(1322);expect(c.journey.outbound.booking_status).toBe('planned');expect(request.journey.outbound.booking_status).toBe('booked');expect(c.journey.inbound).toBeNull();w.unmount()})
 it('invalidates review after a price edit and after new pasted text',async()=>{const w=await preview();await w.get('.ticket-preview .confirm input[type=checkbox]').setValue(true);await field(w,'识别金额').setValue('100');expect(button(w,'确认这段车票').attributes('disabled')).toBeDefined();await field(w,'车票文字').setValue('G10');expect(w.find('.ticket-preview').exists()).toBe(false);w.unmount()})
 it('does not emit when the comparison is full or disabled',async()=>{const w=await preview();await w.get('.ticket-preview .confirm input[type=checkbox]').setValue(true);await w.setProps({disabled:true});await button(w,'确认这段车票').trigger('click');expect(w.emitted('add')).toBeUndefined();w.unmount()})
})

it('invalidates confirmed pending imports and refreshes query defaults after the trip scope changes',async()=>{
 const w=await preview();await w.get('.ticket-preview .confirm input[type=checkbox]').setValue(true)
 await button(w,'确认这段车票').trigger('click');await flushPromises()
 expect(w.find('.pending').exists()).toBe(true)
 await w.setProps({request:{...request,city:'杭州',start_date:'2026-11-01',end_date:'2026-11-03',companions:{count:3}}});await flushPromises()
 expect(w.find('.pending').exists()).toBe(false)
 expect(field(w,'查询出发日期').element.value).toBe('2026-11-01')
 expect(Number(field(w,'查询同行人数').element.value)).toBe(3)
 expect((w.get('textarea[aria-label="查询条件"]').element as HTMLTextAreaElement).value).toContain('目的地：杭州')
 expect(w.emitted('add')).toBeUndefined();w.unmount()
})
