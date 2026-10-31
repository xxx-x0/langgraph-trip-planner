import {mount,flushPromises} from '@vue/test-utils'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import BackgroundTicketSearch from './BackgroundTicketSearch.vue'
import {cancelTicketSearch,continueTicketSearch,getTicketSearch,startTicketSearch} from '@/services/api'
vi.mock('@/services/api',()=>({cancelTicketSearch:vi.fn(),continueTicketSearch:vi.fn(),getTicketSearch:vi.fn(),startTicketSearch:vi.fn()}))
const query={mode:'train' as const,direction:'outbound' as const,from:'上海虹桥',to:'北京南',date:'2026-10-27',passengers:2}
const button=(w:any,s:string)=>w.findAll('button').find((b:any)=>b.text().includes(s))!
beforeEach(()=>{vi.useFakeTimers();vi.resetAllMocks();vi.mocked(cancelTicketSearch).mockResolvedValue({status:'cancelled'});vi.mocked(startTicketSearch).mockResolvedValue({search_id:'one',status:'searching',message:'正在查询'})})
afterEach(()=>{vi.useRealTimers()})
it('queries without an extension, polls and hands candidates to the existing ranking flow',async()=>{
 const w=mount(BackgroundTicketSearch,{props:{query,contextKey:'a'}})
 vi.mocked(getTicketSearch).mockResolvedValue({status:'completed',candidates:[{id:'r1'}],message:'已读取',sampled:true})
 await button(w,'后台查询').trigger('click');await flushPromises();await vi.advanceTimersByTimeAsync(1000)
 expect(startTicketSearch).toHaveBeenCalledWith(expect.objectContaining({from_place:'上海虹桥',passengers:2}),expect.any(AbortSignal))
 expect(w.emitted('candidates')![0][0]).toEqual([{id:'r1'}]);expect(w.text()).toContain('经过采样')
 w.unmount();expect(cancelTicketSearch).toHaveBeenCalledWith('one')
})
it('only opens a browser on the explicit recovery action and can continue after login',async()=>{
 const w=mount(BackgroundTicketSearch,{props:{query:{...query,mode:'flight',from:'上海',to:'北京'},contextKey:'a'}})
 vi.mocked(getTicketSearch).mockResolvedValue({status:'needs_action',message:'请登录'})
 vi.mocked(continueTicketSearch).mockResolvedValue({status:'searching',message:'正在打开'})
 await button(w,'后台查询').trigger('click');await flushPromises();await vi.advanceTimersByTimeAsync(1000)
 expect(continueTicketSearch).not.toHaveBeenCalled()
 await button(w,'打开登录').trigger('click');await flushPromises()
 expect(continueTicketSearch).toHaveBeenCalledWith('one',true,expect.any(AbortSignal))
 vi.mocked(getTicketSearch).mockResolvedValue({status:'needs_action',browser_visible:true,message:'完成后继续'})
 await vi.advanceTimersByTimeAsync(1000)
 await button(w,'继续读取').trigger('click');await flushPromises()
 expect(continueTicketSearch).toHaveBeenLastCalledWith('one',false,expect.any(AbortSignal));w.unmount()
})
it('discards an in-flight response after a scope change and cancels its server job',async()=>{
 let resolve:any;vi.mocked(startTicketSearch).mockReturnValue(new Promise(r=>resolve=r))
 const w=mount(BackgroundTicketSearch,{props:{query,contextKey:'a'}})
 await button(w,'后台查询').trigger('click');await flushPromises()
 const signal=vi.mocked(startTicketSearch).mock.calls[0][1]!
 await w.setProps({contextKey:'b'});expect(signal.aborted).toBe(true)
 resolve({search_id:'late',status:'completed',candidates:[{id:'old'}]});await flushPromises()
 expect(w.emitted('candidates')).toBeUndefined();expect(cancelTicketSearch).toHaveBeenCalledWith('late');w.unmount()
})
it('stops polling and invalidates displayed choices when the query expires',async()=>{
 vi.mocked(startTicketSearch).mockResolvedValue({search_id:'one',status:'completed',candidates:[{id:'r1'}]})
 const w=mount(BackgroundTicketSearch,{props:{query,contextKey:'a'}})
 await button(w,'后台查询').trigger('click');await flushPromises()
 await vi.advanceTimersByTimeAsync(15*60*1000)
 expect(w.text()).toContain('查票已过期');expect(cancelTicketSearch).toHaveBeenCalledWith('one')
 expect(w.emitted('reset')!.length).toBeGreaterThan(1);w.unmount()
})
it('does not turn provider failures or empty lists into recommendations',async()=>{
 const w=mount(BackgroundTicketSearch,{props:{query,contextKey:'a'}})
 vi.mocked(startTicketSearch).mockRejectedValueOnce({response:{data:{detail:'车站未匹配'}}})
 await button(w,'后台查询').trigger('click');await flushPromises();expect(w.text()).toContain('车站未匹配')
 vi.mocked(startTicketSearch).mockResolvedValue({search_id:'one',status:'completed',message:'未读到可用席别',candidates:[]})
 await button(w,'后台查询').trigger('click');await flushPromises()
 expect(w.emitted('candidates')).toBeUndefined();expect(w.text()).toContain('未读到可用席别');w.unmount()
})
it('renders a validation error as a readable message',async()=>{
 vi.mocked(startTicketSearch).mockRejectedValue({response:{data:{detail:[{msg:'Value error, 该地点尚无航班城市代码'}]}}})
 const w=mount(BackgroundTicketSearch,{props:{query,contextKey:'a'}})
 await button(w,'后台查询').trigger('click');await flushPromises()
 expect(w.text()).toContain('该地点尚无航班城市代码');expect(w.text()).not.toContain('[object Object]');w.unmount()
})
it('passes an exact-station scope instead of silently broadening it to a city',async()=>{
 const w=mount(BackgroundTicketSearch,{props:{query:{...query,from:'上海',fromScope:'exact',toScope:'exact'},contextKey:'a'}})
 await button(w,'后台查询').trigger('click');await flushPromises()
 expect(startTicketSearch).toHaveBeenCalledWith(expect.objectContaining({from_place:'上海',from_scope:'exact',to_scope:'exact'}),expect.any(AbortSignal));w.unmount()
})
