import {mount,flushPromises} from '@vue/test-utils'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import BrowserTicketAssistant from './BrowserTicketAssistant.vue'
import {recommendTickets} from '@/services/api'
vi.mock('@/services/api',()=>({recommendTickets:vi.fn()}))
const query={mode:'train' as const,direction:'outbound' as const,from:'上海',to:'北京',date:'2026-10-27',passengers:2}
const candidate={id:'r1',mode:'train',service:'G100',from_station:'上海虹桥',to_station:'北京南',departure:'2026-10-27T08:00',arrival:'2026-10-27T12:30',seat:'二等座',fare_per_person:500}
const result={ranked_by:'ai',message:'AI根据本次偏好筛选',recommendations:[{candidate,leg:{service_number:'G100',ticket_total:null},reasons:['车程4小时30分']}]}
const button=(w:any,s:string)=>w.findAll('button').find((b:any)=>b.text().includes(s))!
let post:ReturnType<typeof vi.spyOn>
function send(id:string,type:string,extra:any={}){window.dispatchEvent(new MessageEvent('message',{source:window,origin:window.location.origin,data:{channel:'ltp-ticket-extension-v1',requestId:id,type,...extra}}))}
async function start(w:any){await button(w,'打开查票').trigger('click');return [...post.mock.calls].reverse().find((c:any)=>c[0].type==='ltp-start')![0].requestId}
beforeEach(()=>{vi.useFakeTimers();vi.mocked(recommendTickets).mockReset();post=vi.spyOn(window,'postMessage').mockImplementation(()=>{})})
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers()})
describe('browser ticket recommendations',()=>{
 it('switches the AI engine, invalidates the previous recommendation, and omits Jev for metric sorting',async()=>{
  vi.mocked(recommendTickets).mockResolvedValueOnce(result)
    .mockResolvedValueOnce({...result,ranked_by:'jev',schedule_basis:'jev-basis'})
    .mockResolvedValueOnce({...result,ranked_by:'metric'})
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
  const priority=w.get('.browser-tickets > label select')
  await priority.setValue('balanced')
  const id=await start(w)
  send(id,'ltp-result',{candidates:[candidate]})
  await flushPromises()
  expect(w.text()).toContain('AI推荐')
  await w.get('.ticket-engine select').setValue('jev')
  expect(w.find('article').exists()).toBe(false)
  await button(w,'重新AI筛选').trigger('click')
  await flushPromises()
  expect(recommendTickets).toHaveBeenLastCalledWith(expect.objectContaining({engine:'jev'}),expect.any(AbortSignal))
  expect(w.text()).toContain('Jev 推荐')
  await button(w,'采用这班').trigger('click')
  expect(w.emitted('adopt')![0][0]).toMatchObject({ticketBasis:'jev-basis'})
  await priority.setValue('time')
  expect(w.find('.ticket-engine').exists()).toBe(false)
  await button(w,'重新筛选').trigger('click')
  await flushPromises()
  expect(recommendTickets).toHaveBeenLastCalledWith(expect.objectContaining({engine:'default'}),expect.any(AbortSignal))
  w.unmount()
 })
 it('labels numeric sorting without offering an AI retry and preserves adoption',async()=>{
  vi.mocked(recommendTickets).mockResolvedValue({...result,ranked_by:'metric',message:'已按已知参考价排列'})
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
  await w.get('select').setValue('price')
  const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
  expect(w.text()).toContain('按所选指标排序')
  expect(button(w,'重新筛选').exists()).toBe(true)
  expect(w.findAll('button').some(b=>b.text()==='重新AI筛选')).toBe(false)
  await button(w,'采用这班').trigger('click')
  expect(w.emitted('adopt')![0][0]).toMatchObject({leg:result.recommendations[0].leg,direction:'outbound'})
  w.unmount()
 })
 it('offers the updated package for an older installed helper and hides it for current or newer versions',async()=>{
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
  send('','ltp-ping-reply',{version:'0.2.1'});await flushPromises()
  expect(w.text()).toContain('更新浏览器查票助手');expect(w.text()).toContain('当前提供 0.2.2')
  expect(w.find('a[download]').exists()).toBe(true)
  send('','ltp-ping-reply',{version:'0.2.2'});await flushPromises()
  expect(w.text()).not.toContain('更新浏览器查票助手')
  send('','ltp-ping-reply',{version:'0.10.0'});await flushPromises()
  expect(w.text()).not.toContain('更新浏览器查票助手');w.unmount()
 })
 it('revokes displayed choices and discards a late model response after a bridge failure',async()=>{
  let resolve:any
  vi.mocked(recommendTickets).mockResolvedValueOnce({...result,schedule_basis:'old',excluded:[{candidate,conflicts:['旧冲突']}]})
    .mockReturnValueOnce(new Promise(r=>resolve=r))
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
  const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
  expect(w.find('article').exists()).toBe(true)
  send(id,'ltp-error',{error:'原查询已失效，请重新查询'});await flushPromises()
  expect(w.find('article').exists()).toBe(false)
  expect(w.text()).not.toContain('旧冲突')
  await button(w,'重新筛选').trigger('click')
  const signal=vi.mocked(recommendTickets).mock.calls[1][1]!
  send(id,'ltp-error',{error:'扩展已更新，请刷新规划页'});await flushPromises()
  expect(signal.aborted).toBe(true)
  resolve(result);await flushPromises()
  expect(w.find('article').exists()).toBe(false)
  expect(w.text()).toContain('扩展已更新')
  expect(w.emitted('adopt')).toBeUndefined();w.unmount()
 })
 it('clears old exclusion facts when the ranking preference changes',async()=>{
  vi.mocked(recommendTickets).mockResolvedValue({...result,schedule_basis:'old',excluded:[{candidate,conflicts:['旧冲突']}]})
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
  const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
  await w.get('select').setValue('price')
  expect(w.find('article').exists()).toBe(false);expect(w.text()).not.toContain('旧冲突')
  expect(w.text()).toContain('偏好已改变');w.unmount()
 })
 it('passes the saved schedule scope and carries the verified basis into adoption',async()=>{const scope={kind:'multi' as const,draft_id:'mc_one',revision:4,from_stop:'b',to_stop:'destination'};vi.mocked(recommendTickets).mockResolvedValue({...result,schedule_basis:'checked-basis',excluded:[{candidate:{...candidate,id:'bad',service:'G1'},conflicts:['含缓冲须04:45前结束，原安排至13:15']} ]});const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a',scheduleContext:scope}});const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(recommendTickets).toHaveBeenCalledWith(expect.objectContaining({context:scope}),expect.any(AbortSignal));expect(w.text()).toContain('1 条需要调整日程的班次');expect(w.text()).toContain('原安排至13:15');await button(w,'采用这班').trigger('click');expect(w.emitted('adopt')![0][0]).toMatchObject({ticketBasis:'checked-basis'});await w.setProps({scheduleContext:{...scope,revision:5}});expect(w.find('article').exists()).toBe(false);w.unmount()})
 it('does not show an adopt button when every candidate conflicts or a snapshot becomes stale',async()=>{vi.mocked(recommendTickets).mockResolvedValueOnce({...result,recommendations:[],message:'当前已读取候选都与已保存安排冲突',excluded:[{candidate,conflicts:['午餐冲突']}]}).mockRejectedValueOnce({response:{status:409}});const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.text()).toContain('午餐冲突');expect(w.find('article').exists()).toBe(false);await button(w,'重新筛选').trigger('click');await flushPromises();expect(w.text()).toContain('安排已改变');expect(w.emitted('adopt')).toBeUndefined();w.unmount()})
 it('reports a website empty result without invoking AI and can receive later results',async()=>{vi.mocked(recommendTickets).mockResolvedValue(result);const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-result',{status:'empty',candidates:[]});await flushPromises();expect(w.text()).toContain('网站当前没有返回可读取候选');expect(recommendTickets).not.toHaveBeenCalled();send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.text()).toContain('AI推荐');w.unmount()})
 it('explains a missing extension without altering saved travel',async()=>{const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});await start(w);await vi.advanceTimersByTimeAsync(2300);expect(w.text()).toContain('未连接到浏览器助手');expect(w.get('a[download]').attributes('href')).toBe('/ticket-assistant-extension.zip');expect(w.emitted('adopt')).toBeUndefined();w.unmount()})
 it('ranks returned candidates then adopts directly without manual fields',async()=>{vi.mocked(recommendTickets).mockResolvedValue(result);const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-start-reply',{started:true});send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.text()).toContain('AI推荐');expect(recommendTickets).toHaveBeenCalledWith(expect.objectContaining({candidates:[candidate]}),expect.any(AbortSignal));expect(w.emitted('adopt')).toBeUndefined();await button(w,'采用这班').trigger('click');expect(w.emitted('adopt')![0][0]).toEqual({leg:result.recommendations[0].leg,direction:'outbound'});w.unmount()})
 it('ignores an old query result and aborts a late model response',async()=>{let resolve:any;vi.mocked(recommendTickets).mockReturnValue(new Promise(r=>resolve=r));const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises();await w.setProps({query:{...query,date:'2026-10-28'}});resolve(result);await flushPromises();send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.find('article').exists()).toBe(false);expect(recommendTickets).toHaveBeenCalledTimes(1);w.unmount()})
 it('invalidates choices when parent trip context changes',async()=>{vi.mocked(recommendTickets).mockResolvedValue(result);const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises();await w.setProps({contextKey:'b'});expect(w.find('article').exists()).toBe(false);w.unmount()})
 it('labels fallback and preserves returned candidates for retry',async()=>{vi.mocked(recommendTickets).mockRejectedValueOnce(new Error('failed')).mockResolvedValueOnce({...result,ranked_by:'rules'});const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.text()).toContain('候选已保留');await button(w,'重新筛选').trigger('click');await flushPromises();expect(w.text()).toContain('规则排序');w.unmount()})
 it('does not start when disabled or a station cannot be mapped',async()=>{const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a',disabled:true}});expect(button(w,'打开查票').attributes('disabled')).toBeDefined();await w.setProps({disabled:false,query:{...query,from:'未知具体住址'}});expect(button(w,'打开查票').attributes('disabled')).toBeDefined();expect(post.mock.calls.filter((c:any)=>c[0].type==='ltp-start')).toHaveLength(0);w.unmount()})
 it('expires old recommendations and ignores later results for that query',async()=>{vi.mocked(recommendTickets).mockResolvedValue(result);const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}});const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.find('article').exists()).toBe(true);await vi.advanceTimersByTimeAsync(15*60*1000);expect(w.text()).toContain('连接已过期');send(id,'ltp-result',{candidates:[candidate]});await flushPromises();expect(w.find('article').exists()).toBe(false);w.unmount()})
 it('offers recovery beside all-conflicting results and keeps each reason collapsed',async()=>{
  vi.mocked(recommendTickets).mockResolvedValue({...result,recommendations:[],excluded:[{candidate,conflicts:['全天安排重叠','原来的餐次须保留']}]})
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a',scheduleContext:{kind:'multi',draft_id:'mc',revision:1,from_stop:'s',to_stop:'h'}},slots:{'conflict-actions':'<button>调整当天安排</button>'}})
  const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
  expect(w.get('.conflict-help').text()).toContain('同步回整趟旅行')
  expect(w.get('.conflict-help button').text()).toBe('调整当天安排')
  expect((w.get('.exclusion-list details').element as HTMLDetailsElement).open).toBe(false)
  expect(w.get('.exclusion-list').text()).toContain('原来的餐次须保留')
  expect(w.emitted('adopt')).toBeUndefined();w.unmount()
 })

 it('offers a distinct adjustment preview for an excluded multi-city ticket without calling it a fit',async()=>{
  vi.mocked(recommendTickets).mockResolvedValue({...result,recommendations:[],schedule_basis:'basis',excluded:[{candidate,leg:result.recommendations[0].leg,conflicts:['当天重叠']}]})
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a',scheduleContext:{kind:'multi',draft_id:'mc',revision:1,from_stop:'s',to_stop:'h'}}})
  const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
  await button(w,'按此班次调整').trigger('click')
  expect(w.emitted('adjust')![0][0]).toEqual({leg:result.recommendations[0].leg,ticketBasis:'basis'})
  expect(w.emitted('adopt')).toBeUndefined();expect(w.text()).toContain('取消的景点、用餐和休息')
  w.unmount()
 })

 it('previews a single-city excluded ticket with its snapshot basis',async()=>{
  vi.mocked(recommendTickets).mockResolvedValue({...result,recommendations:[],schedule_basis:'draft-basis',excluded:[{candidate,leg:result.recommendations[0].leg,conflicts:['午餐冲突']}]})
  const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a',scheduleContext:{kind:'draft',draft_id:'draft-one'}}})
  const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
  expect(w.text()).toContain('放不下的景点列入待安排');expect(w.text()).not.toContain('同步回整趟旅行')
  await button(w,'按此班次重新安排').trigger('click')
  expect(w.emitted('adjust')![0][0]).toMatchObject({ticketBasis:'draft-basis',direction:'outbound'});expect(w.emitted('adopt')).toBeUndefined()
  expect(w.find('article').exists()).toBe(false);w.unmount()
 })

})

it('rejects a late model answer after an explicit website empty result',async()=>{
 let resolve:any;vi.mocked(recommendTickets).mockReturnValue(new Promise(r=>resolve=r))
 const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
 const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
 const signal=vi.mocked(recommendTickets).mock.calls[0][1]!
 send(id,'ltp-result',{status:'empty',candidates:[]});await flushPromises()
 resolve(result);await flushPromises()
 expect(signal.aborted).toBe(true);expect(w.find('article').exists()).toBe(false)
 expect(w.text()).toContain('网站当前没有返回可读取候选');expect(w.emitted('adopt')).toBeUndefined();w.unmount()
})

it('defaults to alternatives, shows an actual adjustment and does not add a confirmation dialog',async()=>{
 vi.mocked(recommendTickets).mockResolvedValue({...result,ranked_by:'options',preference_status:'unspecified',recommendations:[{...result.recommendations[0],fit_status:'requires_adjustment',badges:['车程较短'],adjustments:[{date:'2026-10-27',city:'北京',kind:'attraction',ref_name:'公园',before:'11:00',after:'11:10',shift_minutes:10}]}]})
 const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
 expect((w.get('select').element as HTMLSelectElement).value).toBe('unspecified')
 const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
 expect(vi.mocked(recommendTickets).mock.calls[0][0]).toMatchObject({query:{priority:'unspecified'}})
 expect(w.text()).toContain('不同取舍');expect(w.text()).toContain('11:00 → 11:10');expect(w.text()).toContain('需调整后可用')
 await button(w,'采用这班').trigger('click');expect(w.emitted('adopt')).toHaveLength(1);w.unmount()
})

it('keeps unmatched preference conditions out of itinerary-conflict adjustment actions',async()=>{
 vi.mocked(recommendTickets).mockResolvedValue({...result,recommendations:[],preference_excluded:[{candidate,reasons:['不符合本次指定席别；未自动降级']}]})
 const w=mount(BrowserTicketAssistant,{props:{query,contextKey:'a'}})
 const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
 expect(w.text()).toContain('未自动放宽条件');expect(w.text()).not.toContain('本次候选都放不进当前安排')
 expect(w.find('article').exists()).toBe(false);expect(w.emitted('adopt')).toBeUndefined();w.unmount()
})

it('offers a transport-first single-city preview without replacing normal conflict inspection',async()=>{
 vi.mocked(recommendTickets).mockResolvedValue({...result,recommendations:[],schedule_basis:'basis',excluded:[{candidate,leg:result.recommendations[0].leg,conflicts:['全天交通占用']} ]})
 const w=mount(BrowserTicketAssistant,{props:{query:{...query,direction:'inbound'},contextKey:'a',scheduleContext:{kind:'draft',draft_id:'draft-one'}}})
 const id=await start(w);send(id,'ltp-result',{candidates:[candidate]});await flushPromises()
 await button(w,'按此班次重新安排').trigger('click')
 expect(w.emitted('adjust')![0][0]).toEqual({leg:result.recommendations[0].leg,ticketBasis:'basis',direction:'inbound'})
 expect(w.emitted('adopt')).toBeUndefined();w.unmount()
})
