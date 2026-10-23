import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Antd, { DatePicker, Form } from 'ant-design-vue'
import dayjs from 'dayjs'
import Home from './Home.vue'
const navigation=vi.hoisted(()=>({push:vi.fn()}))
vi.mock('vue-router',()=>({useRouter:()=>navigation}))
vi.mock('@/services/api',()=>({previewJourney:vi.fn(async()=>({days:[]}))}))
function setup(){return mount(Home,{global:{plugins:[Antd]}})}
async function dates(w:any,start='2026-10-30',end='2026-11-01'){
 const pickers=w.findAllComponents(DatePicker)
 pickers[0].vm.$emit('update:value',dayjs(start));pickers[1].vm.$emit('update:value',dayjs(end));await flushPromises()
}
function request(){return JSON.parse(sessionStorage.getItem('tripFormData')!)}
beforeEach(()=>{sessionStorage.clear();vi.clearAllMocks()})
describe('standalone hotel occupancy input',()=>{
 it('submits explicit solo conditions and preserves the request for discovery',async()=>{
  const w=setup();await dates(w);w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(request().hotel_occupancy).toEqual({room_count:1,adults_per_room:1,children_ages:[]})
  expect(navigation.push).toHaveBeenCalledWith('/discover');w.unmount()
 })
 it('does not attach overnight conditions to a day trip',async()=>{
  const w=setup();await dates(w,'2026-10-30','2026-10-30');w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(request().hotel_occupancy).toBeUndefined();expect(w.find('.stay-with-party').exists()).toBe(false);w.unmount()
 })
 it('blocks inconsistent room totals then submits the corrected multi-room request',async()=>{
  const w=setup();await dates(w);await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  await w.find('input[aria-label="房间数"]').setValue('2');await flushPromises()
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(navigation.push).not.toHaveBeenCalled();expect(sessionStorage.getItem('tripFormData')).toBeNull()
  await w.find('input[aria-label="每间房成人数"]').setValue('1');w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(request().hotel_occupancy).toEqual({room_count:2,adults_per_room:1,children_ages:[]});w.unmount()
 })
 it('rejects invalid child ages and passes a matching child occupancy',async()=>{
  const w=setup();await dates(w);await w.find('input[aria-label="出行人数"]').setValue('3');await flushPromises()
  await w.find('input[aria-label="每间房成人数"]').setValue('2');await w.find('input[aria-label="每间房儿童年龄"]').setValue('18')
  w.findComponent(Form).vm.$emit('finish');await flushPromises();expect(navigation.push).not.toHaveBeenCalled()
  await w.find('input[aria-label="每间房儿童年龄"]').setValue('8');w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(request().hotel_occupancy).toEqual({room_count:1,adults_per_room:2,children_ages:[8]});w.unmount()
 })
 it('switches to solo without retaining hidden group or child values',async()=>{
  const w=setup();await dates(w);await w.find('input[aria-label="出行人数"]').setValue('2');await flushPromises()
  await w.find('input[aria-label="房间数"]').setValue('2');await w.find('input[aria-label="每间房儿童年龄"]').setValue('8')
  await w.find('input[aria-label="出行人数"]').setValue('1');await flushPromises()
  w.findComponent(Form).vm.$emit('finish');await flushPromises()
  expect(request().hotel_occupancy).toEqual({room_count:1,adults_per_room:1,children_ages:[]});w.unmount()
 })
})
