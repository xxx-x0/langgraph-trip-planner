import {mount,flushPromises} from '@vue/test-utils'
import {describe,it,expect,vi,beforeEach} from 'vitest'
import Antd,{DatePicker,Form} from 'ant-design-vue'
import dayjs from 'dayjs'
import Home from './Home.vue'
import JourneyEditor from '@/components/JourneyEditor.vue'
import {previewJourney} from '@/services/api'
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}))
vi.mock('@/services/api',()=>({previewJourney:vi.fn(async()=>({days:[]}))}))
const setup=()=>mount(Home,{global:{plugins:[Antd],stubs:{'router-link':{template:'<a><slot /></a>'}}}})
async function dates(w:any,start='2026-10-30',end='2026-11-01'){
 const pickers=w.findAllComponents(DatePicker)
 pickers[0].vm.$emit('update:value',dayjs(start));pickers[1].vm.$emit('update:value',dayjs(end));await flushPromises()
}
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear()})
describe('party and stay setup',()=>{
 it('puts room allocation inside party settings only for overnight groups',async()=>{
  const w=setup();await dates(w)
  expect(w.find('[aria-label="房间数"]').exists()).toBe(false)
  await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  expect(w.find('.stay-with-party [aria-label="房间数"]').exists()).toBe(true)
  expect((w.find('input[aria-label="每间房成人数"]').element as HTMLInputElement).value).toBe('2')
  await dates(w,'2026-10-30','2026-10-30')
  expect(w.find('.stay-with-party').exists()).toBe(false)
  w.unmount()
 })
 it('ignores hidden group room values after returning to solo and sends the solo occupancy',async()=>{
  const w=setup();await dates(w)
  await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  await w.find('input[aria-label="房间数"]').setValue('2')
  await w.find('input[aria-label="每间房儿童年龄"]').setValue('8')
  await w.find('input[aria-label="出行人数"]').setValue('1');await flushPromises()
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(vi.mocked(previewJourney).mock.calls.at(-1)?.[0].hotel_occupancy).toEqual({room_count:1,adults_per_room:1,children_ages:[]})
  w.unmount()
 })
 it('updates unquoted transport party size but preserves quoted passenger counts for review',async()=>{
  const w=setup()
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  await w.findAll('.mode-choices button').find(b=>b.text()==='铁路')!.trigger('click')
  await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  const editor=w.findComponent(JourneyEditor)
  expect(editor.props('modelValue')?.outbound?.passengers).toBe(2)
  const quoted=JSON.parse(JSON.stringify(editor.props('modelValue')))
  quoted.outbound.ticket_total=200;quoted.outbound.price_source='user_estimate'
  editor.vm.$emit('update:modelValue',quoted);await flushPromises()
  await w.find('input[aria-label="出行人数"]').setValue('3');await flushPromises()
  expect(editor.props('modelValue')?.outbound?.passengers).toBe(2)
  expect(editor.text()).toContain('与本次 3 人同行不同')
  w.unmount()
 })
 it('blocks inconsistent room totals before preview and does not send partial transport',async()=>{
  const w=setup();await dates(w)
  await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  await w.find('input[aria-label="房间数"]').setValue('2');await flushPromises()
  expect(w.find('.setup-error').text()).toContain('总人数')
  w.findComponent(Form).vm.$emit('finish');await flushPromises();expect(previewJourney).not.toHaveBeenCalled()
  await w.find('input[aria-label="房间数"]').setValue('1')
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  await w.findAll('.mode-choices button').find(b=>b.text()==='铁路')!.trigger('click')
  w.findComponent(Form).vm.$emit('finish');await flushPromises();expect(previewJourney).not.toHaveBeenCalled()
  await w.findAll('.mode-choices button').find(b=>b.text()==='稍后确定')!.trigger('click')
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(vi.mocked(previewJourney).mock.calls.at(-1)?.[0].journey).toMatchObject({origin_city:'杭州',return_city:'杭州',outbound:null})
  w.unmount()
 })
 it('keeps the automatic return city after party updates, but respects an explicit return city',async()=>{
  const w=setup()
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  await w.findAll('.mode-choices button').find(b=>b.text()==='飞机')!.trigger('click')
  await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  await w.find('input[aria-label="出发城市"]').setValue('上海')
  expect(w.findComponent(JourneyEditor).props('modelValue')?.return_city).toBe('上海')
  await w.find('input[aria-label="返回城市"]').setValue('南京')
  await w.find('input[aria-label="出行人数"]').setValue('3');await flushPromises()
  await w.find('input[aria-label="出发城市"]').setValue('杭州')
  expect(w.findComponent(JourneyEditor).props('modelValue')?.return_city).toBe('南京')
  w.unmount()
 })
 it('switches twin room allocations atomically and submits total budget unchanged',async()=>{
  const w=setup();await dates(w)
  await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  await w.find('input[placeholder="不限预算"]').setValue('5000')
  await w.findAll('.room-presets button')[1].trigger('click')
  expect(w.find('.setup-error').exists()).toBe(false)
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(vi.mocked(previewJourney).mock.calls.at(-1)?.[0]).toMatchObject({budget:5000,hotel_occupancy:{room_count:2,adults_per_room:1,children_ages:[]}})
  await w.findAll('.room-presets button')[0].trigger('click')
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(vi.mocked(previewJourney).mock.calls.at(-1)?.[0].hotel_occupancy?.adults_per_room).toBe(2)
  w.unmount()
 })
 it('prevents duplicate preview requests while pending',async()=>{
  const w=setup();await dates(w)
  let finish!: (v:any)=>void
  vi.mocked(previewJourney).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  w.findComponent(Form).vm.$emit('finish')
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(previewJourney).toHaveBeenCalledTimes(1)
  expect(w.find('button[type="submit"]').attributes('disabled')).toBeDefined()
  finish({days:[]});await flushPromises();w.unmount()
 })

})
