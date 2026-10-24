import {mount,flushPromises} from '@vue/test-utils'
import {describe,it,expect,vi,beforeEach} from 'vitest'
import MultiTripView from './MultiTripView.vue'
const mock=vi.hoisted(()=>({api:vi.fn(),push:vi.fn(),leave:vi.fn(),update:vi.fn(),route:{params:{} as any,query:{}}}))
vi.mock('@/services/api',()=>({multiApi:mock.api}))
vi.mock('vue-router',()=>({useRoute:()=>mock.route,useRouter:()=>({push:mock.push}),onBeforeRouteLeave:mock.leave,onBeforeRouteUpdate:mock.update}))
const plan={title:'验证行程',start_date:'2026-10-20',end_date:'2026-10-26',origin:{id:'o',name:'上海'},destination:{id:'r',name:'上海'},companions:{type:'solo',count:1},hotel_occupancy:null,budget:2000,pace:'balanced',preferences:[],stops:[{id:'s',city:{id:'sz',name:'苏州'},start_date:'2026-10-20',end_date:'2026-10-23',must_visit:true,lodgings:[]},{id:'h',city:{id:'hz',name:'杭州'},start_date:'2026-10-23',end_date:'2026-10-26',must_visit:true,lodgings:[]}],transfers:[]}
const summary={description:'当前事实说明',cities:[{id:'s',city:'苏州',nights:3,windows:[],days:[],source_draft:null}],nights:[],conflicts:[],missing:['价格待核对'],budget:{total:0,transport:0,hotels:0,local:0,complete:false},door_minutes:null,hotel_changes:1}
const doc={id:'mc_test',revision:1,status:'draft',plan,summary}
const mountView=()=>mount(MultiTripView,{attachTo:document.body,global:{stubs:{RouterLink:{template:'<a><slot /></a>'},TicketAssistant:true,JourneyEditor:true}}})
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text().includes(text))!
const field=(w:any,text:string)=>w.findAll('label').find((b:any)=>b.text().startsWith(text))!.find('input,select')
beforeEach(()=>{mock.route.query={};mock.route.params={id:'mc_test'};mock.api.mockReset();mock.push.mockReset();mock.api.mockResolvedValue(structuredClone(doc));sessionStorage.clear()})
describe('whole-trip planning',()=>{
 it('shows saved ticket facts in the read-only whole-trip version',async()=>{mock.api.mockResolvedValue({...doc,status:'saved',plan:{...plan,transfers:[{from_stop:'origin',to_stop:'s',leg:{service_number:'G100',booking_status:'booked',departure_station:'上海虹桥',arrival_station:'苏州',departure_time:'2026-10-20T10:00',arrival_time:'2026-10-20T11:00',passengers:1,ticket_total:35,currency:'CNY',price_note:'测试报价'}}]},summary:{...summary,transfers:[{from_stop:'origin',to_stop:'s',from_city:'上海',to_city:'苏州',minutes:150}]}});const w=mountView();await flushPromises();expect(w.text()).toContain('G100');expect(w.text()).toContain('上海虹桥 2026-10-20 10:00');expect(w.text()).toContain('测试报价');w.unmount()})

 it('fills rest suggestions without saving and requires a new preview',async()=>{const w=mountView();await flushPromises();const proposed=structuredClone(plan) as any;proposed.stops[0].rest_periods=[{id:'rest1',date:'2026-10-22',start_time:'14:00',end_time:'17:00',label:'下午休息'}];mock.api.mockResolvedValue({plan:proposed,notes:[]});await button(w,'帮我留出休息').trigger('click');await flushPromises();expect(field(w,'休息日期').element.value).toBe('2026-10-22');expect(w.text()).toContain('尚未保存');expect(button(w,'选择景点并安排').attributes('disabled')).toBeDefined();expect(mock.api.mock.calls.filter(c=>c[1]==='put')).toHaveLength(0);await button(w,'移除这段休息').trigger('click');expect(w.text()).not.toContain('休息开始');w.unmount()})
 it('invalidates old city comparisons when input changes',async()=>{const w=mountView();await flushPromises();mock.api.mockResolvedValue({options:[{name:'反向',reason:'测试',plan,summary,blocked:[]}]});await button(w,'比较城市级').trigger('click');await flushPromises();expect(w.text()).toContain('先比较怎么走');await field(w,'旅行名称').setValue('新名称');expect(w.text()).not.toContain('先比较怎么走');w.unmount()})

 it('requires preview and invalidates it when the draft changes',async()=>{const w=mountView();await flushPromises();await field(w,'总预算').setValue('2500');expect(button(w,'选择景点并安排').attributes('disabled')).toBeDefined();mock.api.mockResolvedValue({preview_token:'p',changes:['预算变化'],booked:[],budget_delta:0,summary});await button(w,'查看整趟变更').trigger('click');await flushPromises();expect(w.text()).toContain('确认后，这些地方');await field(w,'旅行名称').setValue('再改名称');expect(w.find('.preview').exists()).toBe(false);w.unmount()})
 it('shows save failure without replacing the saved summary',async()=>{const w=mountView();await flushPromises();mock.api.mockRejectedValue({response:{data:{detail:'版本已变化'}}});await button(w,'查看整趟变更').trigger('click');await flushPromises();expect(w.text()).toContain('版本已变化');expect(w.text()).toContain('当前事实说明');expect(w.find('.preview').exists()).toBe(false);w.unmount()})
 it('keeps saved versions read only and provides a copy action',async()=>{mock.api.mockResolvedValue({...doc,status:'saved'});const w=mountView();await flushPromises();expect(w.get('fieldset.card').attributes('disabled')).toBeDefined();expect(button(w,'复制为新版本')).toBeDefined();expect(w.text()).not.toContain('将当前安排同步');w.unmount()})
 it('passes an exact parent revision and city basis into discovery',async()=>{const w=mountView();await flushPromises();mock.api.mockResolvedValue({request:{city:'苏州'},basis:'abc',revision:1});await button(w,'选择景点并安排').trigger('click');await flushPromises();expect(mock.push).toHaveBeenCalledWith({path:'/discover',query:{multi:'mc_test',stop:'s',basis:'abc',revision:'1'}});expect(JSON.parse(sessionStorage.getItem('tripFormData')!)).toEqual({city:'苏州'});w.unmount()})
 it('does not offer adopting a change to booked arrangements',async()=>{const w=mountView();await flushPromises();mock.api.mockResolvedValue({options:[{name:'反向',reason:'须改签',plan,summary,blocked:['已订班次G1']}]});await button(w,'比较城市级').trigger('click');await flushPromises();expect(button(w,'采用这组').attributes('disabled')).toBeDefined();w.unmount()})
 it('switches workspaces without losing unsaved input or making a write',async()=>{const w=mountView();await flushPromises();expect(w.get('.overview-panel').isVisible()).toBe(true);expect(w.get('fieldset.card').isVisible()).toBe(false);await button(w,'城市与住宿').trigger('click');await field(w,'旅行名称').setValue('我想慢慢逛');await button(w,'城际交通').trigger('click');expect(w.get('.transport-panel').isVisible()).toBe(true);expect(w.get('.save-dock').text()).toContain('尚未保存');await button(w,'城市与住宿').trigger('click');expect((field(w,'旅行名称').element as HTMLInputElement).value).toBe('我想慢慢逛');expect(mock.api.mock.calls.some(c=>c[1]==='put')).toBe(false);w.unmount()})
 it('keeps a preview visible across workspaces and requires booked acknowledgement',async()=>{const w=mountView();await flushPromises();await field(w,'总预算').setValue('2500');mock.api.mockResolvedValue({preview_token:'p',changes:['预算变化'],booked:['已订住宿'],budget_delta:0,summary});await button(w,'查看整趟变更').trigger('click');await flushPromises();await button(w,'城际交通').trigger('click');expect(w.get('.preview').isVisible()).toBe(true);expect(button(w,'确认影响并保存').attributes('disabled')).toBeDefined();await w.get('.preview input[type=checkbox]').setValue(true);expect(button(w,'确认影响并保存').attributes('disabled')).toBeUndefined();w.unmount()})
 it('shows a failed load without exposing a different editable sample plan',async()=>{mock.api.mockRejectedValue(new Error('offline'));const w=mountView();await flushPromises();expect(w.get('[role=alert]').text()).toContain('读取失败');expect(w.find('fieldset').exists()).toBe(false);w.unmount()})
 it('blocks a shortened trip before preview and focuses the invalid city date',async()=>{
   const w=mountView();await flushPromises()
   await w.get('#trip-end').setValue('2026-10-24')
   await button(w,'查看整趟变更').trigger('click');await flushPromises()
   expect(w.get('.input-issues').text()).toContain('杭州离开日期超出旅行范围')
   expect(w.get('fieldset.card').isVisible()).toBe(true)
   expect(mock.api.mock.calls.some(c=>c[0].endsWith('/preview'))).toBe(false)
   await w.get('.input-issues button').trigger('click');await flushPromises()
   expect(document.activeElement?.id).toBe('city-end-h')
   w.unmount()
 })
 it('only asks to leave when there are unsaved changes',async()=>{
   const confirm=vi.fn().mockReturnValue(false)
   vi.stubGlobal('confirm',confirm)
   const w=mountView();await flushPromises()
   const guard=mock.leave.mock.calls.at(-1)![0]
   expect(guard()).toBe(true)
   await field(w,'总预算').setValue('2500')
   expect(guard()).toBe(false)
   expect(confirm).toHaveBeenCalledOnce()
   vi.unstubAllGlobals();w.unmount()
 })
 it('opens the suggested rest periods so their times can be reviewed',async()=>{
   const w=mountView();await flushPromises()
   mock.api.mockResolvedValue({plan:{...plan,stops:plan.stops.map((s,i)=>({...s,rest_periods:i?[]:[{id:'r',date:'2026-10-22',start_time:'14:00',end_time:'16:00'}]}))},notes:[]})
   await button(w,'帮我留出休息').trigger('click');await flushPromises()
   expect((w.get('#rest-s').element as HTMLDetailsElement).open).toBe(true)
   expect((w.get('#rest-h').element as HTMLDetailsElement).open).toBe(false)
   w.unmount()
 })
 it('explains that keeping a conflicting preview does not make it a saved travel version',async()=>{
   const w=mountView();await flushPromises()
   mock.api.mockResolvedValue({preview_token:'conflict',changes:[],booked:[],budget_delta:0,summary:{...summary,conflicts:['苏州回酒店时间与出发缓冲冲突']}})
   await button(w,'查看整趟变更').trigger('click');await flushPromises()
   expect(w.get('.preview-conflicts').text()).toContain('1 处时间冲突')
   expect(w.get('.preview-conflicts').text()).toContain('冲突解决前不能保存为旅行版本')
   expect(button(w,'保留为草稿，稍后处理冲突')).toBeDefined()
   w.unmount()
 })
 it('groups every pending item without dropping unknown costs and provides a transport shortcut',async()=>{
   const missing=['苏州 → 杭州班次待确认','入住配置未确认','早餐未安排','留园门票','价格待核对']
   mock.api.mockResolvedValue({...doc,summary:{...summary,missing}})
   const w=mountView();await flushPromises()
   expect(w.findAll('.checklist-group')).toHaveLength(5)
   expect(w.findAll('.checklist-group li').map(item=>item.text())).toEqual(missing)
   expect(w.findAll('.checklist-group').every(group=>!(group.element as HTMLDetailsElement).open)).toBe(true)
   await button(w,'去安排交通').trigger('click')
   expect(w.get('.transport-panel').isVisible()).toBe(true)
   w.unmount()
 })
 it('opens the relevant city date and returns to the selected transport segment',async()=>{
  mock.route.query={section:'transport',edge:'0'}
  mock.api.mockResolvedValue({...doc,summary:{...summary,cities:[{...summary.cities[0],source_draft:'city',days:[{date:'2026-10-20',timeline_schedule:[{kind:'attraction',start_time:'10:00',end_time:'12:00'}]}]}]}})
  const w=mountView();await flushPromises()
  expect(w.get('.transport-panel').isVisible()).toBe(true)
  expect(w.get('.edge-day-context').text()).toContain('10:00—12:00')
  mock.api.mockResolvedValue({draft_id:'copy',basis:'basis',revision:1})
  await button(w,'调整 苏州 当天安排').trigger('click');await flushPromises()
  expect(mock.push).toHaveBeenCalledWith({path:'/draft/copy',query:{multi:'mc_test',stop:'s',basis:'basis',revision:'1',date:'2026-10-20',returnSection:'transport',edge:'0'}})
  w.unmount()
 })
 it('previews manual buffer edits directly without adding a comparison',async()=>{
  const w=mountView();await flushPromises()
  const leg={service_number:'G1388',departure_station:'杭州东',arrival_station:'上海虹桥',departure_time:'2026-10-20T21:49',arrival_time:'2026-10-20T22:48',transfer_before_minutes:90}
  w.findComponent({name:'JourneyEditor'}).vm.$emit('update:modelValue',{outbound:leg});await flushPromises()
  mock.api.mockResolvedValue({preview_token:'p',changes:[],booked:[],summary,budget_delta:0})
  await button(w,'预览本段修改').trigger('click');await flushPromises()
  expect(mock.api.mock.calls.find(c=>c[0]==='/mc_test/preview')?.[2].plan.transfers[0].leg.transfer_before_minutes).toBe(90)
  expect(w.findAll('.options article')).toHaveLength(0)
  w.unmount()
 })
 it('protects manual inputs from being lost when switching traffic segments',async()=>{
  const confirm=vi.fn().mockReturnValue(false);vi.stubGlobal('confirm',confirm)
  const w=mountView();await flushPromises()
  w.findComponent({name:'JourneyEditor'}).vm.$emit('update:modelValue',{outbound:{service_number:'unsaved'}});await flushPromises()
  await w.get('.edge-picker button:nth-child(2)').trigger('click')
  expect(confirm).toHaveBeenCalledOnce()
  expect(w.get('.edge-picker button').attributes('aria-pressed')).toBe('true')
  expect(w.get('.save-dock').text()).toContain('尚未保存')
  vi.unstubAllGlobals();w.unmount()
 })

})

describe('journey desk controls',()=>{
 it('redistributes a shared city boundary locally and preserves saved tickets until preview',async()=>{
  const original=structuredClone(doc) as any;original.plan.transfers=[{from_stop:'s',to_stop:'h',leg:{service_number:'G8359'}}];mock.api.mockResolvedValue(original)
  const w=mountView();await flushPromises();await w.get('#boundary-s').setValue('2')
  expect((w.get('#city-end-s').element as HTMLInputElement).value).toBe('2026-10-22')
  expect((w.get('#city-start-h').element as HTMLInputElement).value).toBe('2026-10-22')
  expect(w.text()).toContain('G8359');expect(w.find('.save-dock').exists()).toBe(true)
  expect(mock.api.mock.calls.some(c=>c[1]==='put')).toBe(false);w.unmount()
 })
 it('uses a shortcut to update only the selected transfer buffer and preview remains explicit',async()=>{
  const w=mountView();await flushPromises();const stage=w.findComponent({name:'TransportStage'});
  w.findComponent({name:'JourneyEditor'}).vm.$emit('update:modelValue',{outbound:{service_number:'G1',transfer_before_minutes:60,departure_time:'2026-10-20T10:00',arrival_time:'2026-10-20T11:00'}});await flushPromises()
  stage.vm.$emit('buffer',{key:'transfer_before_minutes',value:75});await flushPromises()
  expect(w.get('.buffer-preview-action').text()).toContain('尚未保存');expect(mock.api.mock.calls.some(c=>c[0].endsWith('/preview'))).toBe(false)
  mock.api.mockResolvedValue({preview_token:'p',changes:[],booked:[],summary,budget_delta:0});await button(w,'预览新的衔接安排').trigger('click');await flushPromises()
  expect(mock.api.mock.calls.find(c=>c[0].endsWith('/preview'))![2].plan.transfers[0].leg.transfer_before_minutes).toBe(75);w.unmount()
 })
})


it('manually previews active two-city adjustment and requires cancellation acknowledgement',async()=>{
 const w=mountView();await flushPromises()
 const leg={service_number:'G1',departure_station:'苏州',arrival_station:'杭州',departure_time:'2026-10-23T15:00',arrival_time:'2026-10-23T16:00'}
 w.findComponent({name:'JourneyEditor'}).vm.$emit('update:modelValue',{outbound:leg});await flushPromises()
 const proposed=structuredClone(plan) as any;proposed.transfers=[{from_stop:'origin',to_stop:'s',leg}]
 mock.api.mockResolvedValue({preview_token:'checked',adjustment_id:'server-only',proposed_plan:proposed,changes:[],booked:[],adjustments:['取消明确列出的活动'],summary,budget_delta:0})
 await button(w,'按此班次调整两侧当天安排').trigger('click');await flushPromises()
 expect(mock.api.mock.calls.find(c=>c[0]==='/mc_test/preview')![2]).toMatchObject({adjust_days:true,revision:1})
 expect(button(w,'确认影响并保存').attributes('disabled')).toBeDefined()
 await w.get('.adjustment-review input').setValue(true)
 mock.api.mockResolvedValue({...doc,plan:proposed,revision:2})
 await button(w,'确认影响并保存').trigger('click');await flushPromises()
 expect(mock.api.mock.calls.find(c=>c[1]==='put')![2]).toMatchObject({adjustment_id:'server-only',acknowledge_adjustments:true,preview_token:'checked'})
 w.unmount()
})

it('does not restore a preview after manual input changes while it is pending',async()=>{
 const w=mountView();await flushPromises();let finish!:(v:any)=>void
 mock.api.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await button(w,'查看整趟变更').trigger('click')
 w.findComponent({name:'JourneyEditor'}).vm.$emit('update:modelValue',{outbound:{service_number:'new input'}});await flushPromises()
 finish({preview_token:'old',changes:[],booked:[],summary,budget_delta:0});await flushPromises()
 expect(w.find('.preview').exists()).toBe(false)
 expect(mock.api.mock.calls.some(c=>c[1]==='put')).toBe(false)
 w.unmount()
})
