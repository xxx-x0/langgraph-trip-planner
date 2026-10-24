import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import TransportStage from './TransportStage.vue'
const edge={from:'s',to:'h',fromName:'苏州',toName:'杭州',date:'2026-10-29'}
const leg={service_number:'G8359',departure_time:'2026-10-29T15:08',arrival_time:'2026-10-29T15:58',transfer_before_minutes:60,station_buffer_minutes:45,transfer_after_minutes:60,ticket_total:null}
const days=[{id:'s',city:'苏州',period:'08:00—12:42',items:[{start_time:'08:14',end_time:'10:44',ref_name:'拙政园'}]},{id:'h',city:'杭州',period:'17:28—20:00',items:[{start_time:'18:15',end_time:'19:15',ref_name:'新周记晚餐'}]}]
const make=(extra={})=>mount(TransportStage,{props:{edge,leg,days,disabled:false,...extra},global:{stubs:{transition:true}}})
describe('transport stage interaction',()=>{
 it('shows saved travel deadlines even in a read-only version',async()=>{const w=make({readonly:true,days:[{...days[0],window:{end_minutes:568}},{...days[1],window:{start_minutes:927}}]});await w.findAll('.phase-switch button')[0]!.trigger('click');expect(w.get('.stage-deadline').text()).toContain('09:28 前结束市内安排');await w.findAll('.phase-switch button')[2]!.trigger('click');expect(w.get('.stage-deadline').text()).toContain('15:27 后可开始市内安排')})
 it('connects each city phase to the correct stored day and leaves unknown fares unknown',async()=>{const w=make();expect(w.text()).toContain('全体票价 待确认');await w.findAll('.phase-switch button')[0]!.trigger('click');expect(w.text()).toContain('拙政园');expect(w.text()).not.toContain('新周记晚餐');await w.get('.stage-edit').trigger('click');expect(w.emitted('edit')).toEqual([['s']]);await w.findAll('.phase-switch button')[2]!.trigger('click');expect(w.text()).toContain('新周记晚餐');expect(w.text()).not.toContain('拙政园')})
 it('emits a local buffer edit without mutating the saved leg',async()=>{const w=make();await w.get('[aria-label="去车站接驳增加15分钟"]').trigger('click');expect(w.emitted('buffer')).toEqual([[{key:'transfer_before_minutes',value:75}]]);expect(leg.transfer_before_minutes).toBe(60)})
 it('keeps saved versions read only while allowing phase exploration',async()=>{const w=make({readonly:true});expect(w.find('.buffer-controls').exists()).toBe(false);await w.findAll('.phase-switch button')[0]!.trigger('click');expect(w.text()).toContain('拙政园');expect(w.find('.stage-edit').exists()).toBe(false)})
 it('blocks leaving for city editing while buffers are unsaved',async()=>{const w=make({editingDisabled:true});await w.findAll('.phase-switch button')[0]!.trigger('click');expect(w.get('.stage-edit').attributes('disabled')).toBeDefined();expect(w.get('[aria-label="去车站接驳增加15分钟"]').attributes('disabled')).toBeUndefined()})
})
