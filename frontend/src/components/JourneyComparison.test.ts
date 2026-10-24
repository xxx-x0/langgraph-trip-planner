import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,expect,it,vi} from 'vitest'
import JourneyComparison from './JourneyComparison.vue'
import {compareJourneys} from '@/services/api'
vi.mock('@/services/api',()=>({compareJourneys:vi.fn()}))
const request:any={city:'苏州',start_date:'2026-10-19',end_date:'2026-10-20',travel_days:2}
const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
const option:any={index:0,name:'手动高铁',journey,start_date:request.start_date,end_date:request.end_date,badges:[],same_dates:true,known_total:240,cost_complete:false,door_minutes:200,comfort_known:false,connections:0,night_legs:0,transfer_minutes:40,stay_nights:1,available_minutes:700,budget:null,freshness:['去程：需再次核价'],impacts:[],missing:['接驳未知']}
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text().includes(text))!
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear();sessionStorage.setItem('journey-candidates:test',JSON.stringify([{name:'手动高铁',journey,start_date:request.start_date,end_date:request.end_date}]))})
async function open(){vi.mocked(compareJourneys).mockResolvedValue({options:[option]});const w=mount(JourneyComparison,{props:{draftId:'test',request},global:{stubs:{JourneyEditor:true}}});await button(w,'比较这些方案').trigger('click');await flushPromises();return w}
describe('transport comparison',()=>{
 it('adopts a browser recommendation directly into preview and preserves the other leg',async()=>{const w=await open();const saved={...journey,inbound:{service_number:'G101',booking_status:'booked'}};await w.setProps({request:{...request,journey:saved}});const leg={service_number:'G100',departure_station:'上海虹桥',arrival_station:'苏州'};w.findComponent({name:'TicketAssistant'}).vm.$emit('adopt',{leg,direction:'outbound'});expect(w.emitted('choose')![0][0]).toEqual({...saved,outbound:leg});expect(saved).not.toHaveProperty('outbound');w.unmount()})
 it('never saves a candidate automatically and warns about incomplete prices',async()=>{const w=await open();expect(w.emitted('choose')).toBeUndefined();expect(w.text()).toContain('不代表最终总价');await button(w,'选择此方案').trigger('click');expect(w.emitted('choose')![0]).toEqual([journey]);w.unmount()})
 it('adds an imported alternative without changing saved travel',async()=>{const w=await open();w.findComponent({name:'TicketAssistant'}).vm.$emit('add',{name:'导入去程',journey,start_date:request.start_date,end_date:request.end_date});await flushPromises();expect(w.findAll('.candidate-list li')).toHaveLength(2);expect(w.find('article').exists()).toBe(false);expect(w.emitted('choose')).toBeUndefined();expect(w.text()).not.toContain('检查航班');w.unmount()})
 it('cannot apply a nearby-date comparison to the existing trip',async()=>{const w=await open();vi.mocked(compareJourneys).mockResolvedValue({options:[{...option,same_dates:false}]});await button(w,'比较这些方案').trigger('click');await flushPromises();expect(button(w,'选择此方案').attributes('disabled')).toBeDefined();expect(w.text()).toContain('创建新规划');w.unmount()})
 it('keeps the original alternative while its edit is unfinished',async()=>{const w=await open();await button(w,'载入修改').trigger('click');expect(w.find('.candidate-list').text()).toContain('手动高铁');expect(w.find('.comparison > details').attributes('open')).toBeDefined();await w.get('.comparison > details input[maxlength="80"]').setValue('改过的名称');await button(w,'保存备选修改').trigger('click');expect(w.find('.candidate-list').text()).toContain('改过的名称');expect(w.findAll('.candidate-list li')).toHaveLength(1);expect(w.find('article').exists()).toBe(false);w.unmount()})
 it('invalidates old results after saved request changes',async()=>{const w=await open();await w.setProps({request:{...request,journey}});expect(w.find('article').exists()).toBe(false);expect(sessionStorage.getItem('journey-candidates:test')).toContain('手动高铁');w.unmount()})
})


it('clears comparison results when the saved daily schedule changes',async()=>{
 const w=await open();expect(w.find('article').exists()).toBe(true)
 await w.setProps({daysDetail:[{day_start_time:'11:00'}]})
 expect(w.find('article').exists()).toBe(false);w.unmount()
})

it('rejects late comparison results after request or daily facts changed',async()=>{
 const w=await open();let finish!:(v:any)=>void
 vi.mocked(compareJourneys).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await button(w,'比较这些方案').trigger('click')
 await w.setProps({request:{...request,journey},daysDetail:[{day_start_time:'12:00'}]})
 finish({options:[option]});await flushPromises()
 expect(w.find('article').exists()).toBe(false);expect(w.emitted('choose')).toBeUndefined();w.unmount()
})


it('rejects late errors without replacing current comparison state',async()=>{
 const w=await open();let reject!:(v:any)=>void
 vi.mocked(compareJourneys).mockImplementationOnce(()=>new Promise((_resolve,fail)=>{reject=fail}))
 await button(w,'比较这些方案').trigger('click')
 await w.setProps({daysDetail:[{rest_periods:[{id:'new'}]}]})
 reject({response:{data:{detail:'旧请求错误'}}});await flushPromises()
 expect(w.text()).not.toContain('旧请求错误');expect(w.find('article').exists()).toBe(false);w.unmount()
})

it('disables comparison edits while another daily operation is pending',async()=>{
 const w=await open();await w.setProps({disabled:true})
 for(const label of ['载入修改','移除','比较这些方案','选择此方案'])expect(button(w,label).attributes('disabled')).toBeDefined()
 expect(vi.mocked(compareJourneys).mock.calls).toHaveLength(1);w.unmount()
})
