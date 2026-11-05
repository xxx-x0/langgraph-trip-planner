import {mount,flushPromises} from '@vue/test-utils'
import {ref} from 'vue'
import {beforeEach,expect,it,vi} from 'vitest'
import Antd from 'ant-design-vue'
import DiscoverView from './DiscoverView.vue'
import JourneyPlanner from '@/components/JourneyPlanner.vue'
import {previewJourney,previewDayAssignment,createDraftFromSelectionsStream} from '@/services/api'
import SelectableAttractionCard from '@/components/SelectableAttractionCard.vue'

vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()}),useRoute:()=>({query:{}})}))
vi.mock('@/services/api',()=>({previewJourney:vi.fn(),searchAttractionManual:vi.fn(),createDraftFromSelectionsStream:vi.fn(),previewDayAssignment:vi.fn(),loadMoreAttractions:vi.fn(),aiSelectAttractions:vi.fn()}))
vi.mock('@/composables/useTripLoader',()=>({useTripLoader:()=>({state:{phase:'idle'},begin:vi.fn(),dismiss:vi.fn(),setSteady:vi.fn(),updateProgress:vi.fn()})}))
vi.mock('@/composables/useDiscoverySearch',()=>({useDiscoverySearch:()=>({loading:ref(false),loadingMessage:ref(''),loadingProgress:ref(0),elapsedSeconds:ref(0),discoveryNotice:ref(''),search:vi.fn(),stopDiscovery:vi.fn()})}))
const form:any={city:'北京',start_date:'2026-11-10',end_date:'2026-11-12',travel_days:3,transportation:'步行',accommodation:'酒店',journey:{origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai',planning:{arrival_policy:'unreserved',departure_policy:'unreserved'}}}
const attractions=['首日公园','中日景点','末日博物馆'].map((name,i)=>({name,poi_id:String(i),selected:true,visit_minutes:120,category:'历史文化'}))
function setup(){return mount(DiscoverView,{global:{plugins:[Antd],stubs:{JourneyPlanner:true,JourneySummary:true,DiscoveryMap:true,SelectableAttractionCard:true}}})}
const button=(w:any,text:string)=>w.findAll('button').find((b:any)=>b.text().includes(text))!
beforeEach(()=>{
 vi.resetAllMocks();sessionStorage.clear()
 sessionStorage.setItem('tripFormData',JSON.stringify(form))
 sessionStorage.setItem('discoveryRecovery',JSON.stringify({form,attractions,assignments:attractions.map(a=>[a]),durations:[],weather:'',phase:'assign',assignmentEdited:false}))
 sessionStorage.setItem('journeyPreview',JSON.stringify({request:form,days:[0,1,2].map(i=>({date:`2026-11-${10+i}`,window:{start_minutes:0,end_minutes:1440}}))}))
 vi.mocked(createDraftFromSelectionsStream).mockImplementation(async(_form,_selected,_days,_weather,onEvent)=>{onEvent({type:'error',message:'测试：本次未生成，选择保留'})})
})
it('reallocates selected attractions after a transport change and recovers the same choices on refresh',async()=>{
 const windows=[{date:'2026-11-10',window:{start_minutes:1200,end_minutes:1440}},{date:'2026-11-11',window:{start_minutes:0,end_minutes:1440}},{date:'2026-11-12',window:{start_minutes:0,end_minutes:1005}}]
 vi.mocked(previewJourney).mockResolvedValue({days:windows})
 const w=setup();await flushPromises()
 expect(w.findAll('.day-attractions').map(day=>day.text())).toEqual(expect.arrayContaining([expect.stringContaining('首日公园'),expect.stringContaining('末日博物馆')]))
 const next={...form.journey,outbound:{service_number:'G1'}}
 w.findComponent(JourneyPlanner).vm.$emit('update:modelValue',next);await flushPromises()
 expect(w.findAll('.day-attractions')[0].text()).not.toContain('首日公园')
 expect(w.findAll('.day-attractions')[1].text()).toContain('首日公园')
 expect(w.findAll('.day-attractions')[2].text()).toContain('末日博物馆')
 const saved=JSON.parse(sessionStorage.getItem('discoveryRecovery')!)
 expect(saved.attractions.filter((a:any)=>a.selected)).toHaveLength(3)
 expect(saved.form.journey.outbound.service_number).toBe('G1')
 w.unmount()
 const refreshed=setup();await flushPromises()
 expect(refreshed.findAll('.day-attractions')[1].text()).toContain('首日公园')
 expect(refreshed.text()).toContain('20:00—22:00')
 refreshed.unmount()
})
it('preserves the saved selection and transport when the new preview fails',async()=>{
 vi.mocked(previewJourney).mockRejectedValue(new Error('network failure'))
 const w=setup();await flushPromises();const before=sessionStorage.getItem('tripFormData')
 w.findComponent(JourneyPlanner).vm.$emit('update:modelValue',{...form.journey,outbound:{service_number:'bad'}});await flushPromises()
 expect(sessionStorage.getItem('tripFormData')).toBe(before)
 expect(w.findAll('.day-attractions')[0].text()).toContain('首日公园')
 expect(w.text()).toContain('这次交通修改未保存')
 w.unmount()
})

it('plans directly from selected places without a preliminary grouping request or empty-day gate',async()=>{
 const current={...form,journey:null}
 sessionStorage.setItem('tripFormData',JSON.stringify(current))
 sessionStorage.setItem('discoveryRecovery',JSON.stringify({form:current,attractions:[attractions[0]],assignments:[],phase:'discover'}))
 const w=setup();await flushPromises()
 await button(w,'让 AI 安排日程').trigger('click');await flushPromises()
 expect(previewDayAssignment).not.toHaveBeenCalled()
 expect(createDraftFromSelectionsStream).toHaveBeenCalledOnce()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[0][2]).toBeNull()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[0][1].map(a=>a.name)).toEqual(['首日公园'])
 expect(w.find('.discover-layout').exists()).toBe(true)
 expect(w.get('[role="alert"]').text()).toContain('选择保留')
 expect(JSON.parse(sessionStorage.getItem('discoveryRecovery')!).phase).toBe('discover')
 w.unmount()
})

it('does not promote an untouched optional preview to user day assignments',async()=>{
 const w=setup();await flushPromises()
 await button(w,'让 AI 安排日程').trigger('click');await flushPromises()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[0][2]).toBeNull()
 expect(w.find('.assign-layout').exists()).toBe(true)
 w.unmount()
})

it('preserves actual grouping edits on refresh and submits them only after confirmation',async()=>{
 let w=setup();await flushPromises()
 await w.get('select[aria-label="首日公园安排日期"]').setValue('1')
 expect(createDraftFromSelectionsStream).not.toHaveBeenCalled()
 expect(JSON.parse(sessionStorage.getItem('discoveryRecovery')!).assignmentEdited).toBe(true)
 w.unmount();w=setup();await flushPromises()
 expect(w.findAll('.day-attractions')[1].text()).toContain('首日公园')
 await button(w,'按当前分组生成日程').trigger('click');await flushPromises()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[0][2]?.[1].map(a=>a.name)).toContain('首日公园')
 await button(w,'改为 AI 自动安排').trigger('click')
 await button(w,'让 AI 安排日程').trigger('click');await flushPromises()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[1][2]).toBeNull()
 w.unmount()
})

it('keeps manually adjusted groups after a transport change until the user chooses automatic planning',async()=>{
 vi.mocked(previewJourney).mockResolvedValue({days:[{date:'2026-11-10',window:{unavailable:true}},{date:'2026-11-11',window:{}},{date:'2026-11-12',window:{}}]})
 const w=setup();await flushPromises()
 await w.get('select[aria-label="中日景点安排日期"]').setValue('0')
 w.findComponent(JourneyPlanner).vm.$emit('update:modelValue',{...form.journey,outbound:{service_number:'G1'}});await flushPromises()
 expect(w.findAll('.day-attractions')[0].text()).toContain('中日景点')
 expect(w.text()).toContain('当前分组已保留')
 await button(w,'改为 AI 自动安排').trigger('click');await flushPromises()
 expect(w.findAll('.day-attractions')[0].text()).not.toContain('中日景点')
 w.unmount()
})

it('invalidates old grouping edits when the selected places change',async()=>{
 const w=setup();await flushPromises()
 await w.get('select[aria-label="首日公园安排日期"]').setValue('1')
 await button(w,'返回景点选择').trigger('click')
 w.findComponent(SelectableAttractionCard).vm.$emit('toggle',attractions[0]);await flushPromises()
 expect(JSON.parse(sessionStorage.getItem('discoveryRecovery')!).assignmentEdited).toBe(false)
 await button(w,'让 AI 安排日程').trigger('click');await flushPromises()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[0][2]).toBeNull()
 expect(vi.mocked(createDraftFromSelectionsStream).mock.calls[0][1]).toHaveLength(2)
 w.unmount()
})
