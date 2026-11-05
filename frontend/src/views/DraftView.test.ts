import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Antd from 'ant-design-vue'
import DraftView from './DraftView.vue'
import { getDraft, recomputeDay, aiRearrangeDay, multiApi, changeJourney, refreshDiningOptions, adjustJourney, assembleDay } from '@/services/api'

const navigation = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), query: {} as Record<string,string> }))

vi.mock('@/services/api', () => ({
  getDraft: vi.fn(), recomputeDay: vi.fn(), aiRearrangeDay: vi.fn(),
  assembleDay: vi.fn(), rewriteNarrative: vi.fn(), refreshDiningOptions: vi.fn(),
  multiApi: vi.fn(), changeJourney: vi.fn(), adjustJourney: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'draft-test' }, query: navigation.query }),
  useRouter: () => ({ push: navigation.push, replace: navigation.replace }),
}))
vi.mock('@/composables/useTripLoader', () => ({
  useTripLoader: () => ({ state: { phase: 'idle' }, begin: vi.fn(), dismiss: vi.fn() }),
}))

function draft() {
  const attractions = ['A', 'B', 'C', 'D'].map(name => ({ name }))
  return {
    city: '北京', request: { start_date: '2026-10-20', end_date: '2026-10-20', travel_days: 1 },
    days: [{ day_index: 0, date: '2026-10-20', day_start_time: '08:00', attractions, dining_pool: {} }],
    days_detail: [{
      is_assembled: true, attractions, locked_attraction_names: ['B'], removed_attraction_names: [] as string[],
      meals: [], timeline_order: [], day_start_time: '09:00',
    }],
  }
}

async function openDraft() {
  const wrapper = mount(DraftView, { global: {
    plugins: [Antd], stubs: {
      AddDiningPopover: true,
      draggable: {
        name: 'Draggable', props: ['modelValue'], emits: ['update:modelValue', 'end'],
        template: '<div><slot v-for="item in modelValue" name="item" :element="item" /></div>',
      },
    },
  } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.resetAllMocks()
  navigation.query = {}
  vi.mocked(getDraft).mockResolvedValue(draft())
})

describe('saved draft editing', () => {
  it('previews meal refill and retains the opt-in on explicit save, then reloads the saved meals',async()=>{
    const data:any=draft();data.days_detail[0].meals=[{name:'已有午餐',type:'lunch'}]
    vi.mocked(getDraft).mockResolvedValue(data)
    vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'meal-plan',preview_token:'meal-token',days_detail:data.days_detail,impacts:[],changes:[],meal_recovery:[]})
    const w=await openDraft()
    expect(w.get('[aria-label="整体协调行程"]').text()).toContain('还有 1 顿')
    await w.get('[aria-label="整体协调行程"] button').trigger('click');await flushPromises()
    expect(adjustJourney).toHaveBeenCalledWith('draft-test',expect.objectContaining({coordinate_trip:true,refill_meals:true,journey:null}))
    expect(adjustJourney).toHaveBeenCalledTimes(1)
    await w.get('.proposal-ack input').setValue(true)
    vi.mocked(getDraft).mockResolvedValue({...data,days_detail:[{...data.days_detail[0],meals:[...data.days_detail[0].meals,{name:'新晚餐',type:'dinner'}]}]})
    await w.get('.proposal-buttons .primary-action').trigger('click');await flushPromises()
    expect(adjustJourney).toHaveBeenLastCalledWith('draft-test',expect.objectContaining({refill_meals:true,adjustment_id:'meal-plan',preview_token:'meal-token',acknowledge_adjustments:true}))
    expect(w.get('[aria-label="整体协调行程"]').text()).not.toContain('还有 1 顿')
    expect(w.get('[aria-label="整体协调行程"] button').text()).toContain('AI 统筹整趟行程')
    w.unmount()
  })
  it('shows party totals once and cancels a preview without saving',async()=>{
    const data:any=draft();data.request.journey={origin_city:'杭州',return_city:'杭州',destination_timezone:'Asia/Shanghai',outbound:null,inbound:null}
    vi.mocked(getDraft).mockResolvedValue(data)
    vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'joint',preview_token:'token',impacts:[],intercity_total:1140,budget:{total:1894,is_within_budget:null}} as any)
    const w=await openDraft()
    const changed={...data.request.journey,outbound:{service_number:'SC4766',mode:'flight',departure_time:'2026-10-20T10:05',arrival_time:'2026-10-20T11:50',passengers:2,ticket_total:1140,currency:'CNY'}}
    w.findComponent({name:'JourneyComparison'}).vm.$emit('choose',changed,'basis');await flushPromises()
    expect(w.get('.travel-preview .ticket-card').text()).toContain('2 人同行')
    expect(w.get('.travel-preview .ticket-card').text()).toContain('¥1,140')
    expect(w.get('.travel-preview').text()).toContain('不再重复乘人数')
    expect(w.findAll('button').some(b=>b.text().includes('定稿并保存'))).toBe(false)
    expect(w.find('.transport-desk .travel-preview').isVisible()).toBe(true)
    expect(w.find('.transport-search').attributes('style')).toContain('display: none')
    await w.get('.proposal-buttons .secondary-action').trigger('click');await flushPromises()
    expect(w.find('.travel-preview').exists()).toBe(false)
    expect(w.findAllComponents({name:'JourneyEditor'}).at(-1)!.props('modelValue')).toEqual(data.request.journey)
    expect(adjustJourney).toHaveBeenCalledTimes(1)
    expect(w.findAll('button').find(b=>b.text().includes('定稿并保存'))!.attributes('disabled')).toBeUndefined();w.unmount()
  })
  it('makes an explicit meal placement manual and preserves locked and removed activities on failure',async()=>{
    const data:any=draft();data.days_detail[0].removed_attraction_names=['X'];data.days_detail[0].meals=[{name:'午餐店',type:'lunch',schedule_mode:'auto'}];data.days_detail[0].timeline_order=[{kind:'attraction',ref_name:'A'},{kind:'meal',ref_name:'午餐店'}]
    vi.mocked(getDraft).mockResolvedValue(data);vi.mocked(recomputeDay).mockRejectedValue(new Error('route failed'))
    const w=await openDraft();await w.get('[aria-label="午餐店用餐顺序"]').setValue('C');await flushPromises()
    const body:any=vi.mocked(recomputeDay).mock.calls[0]![2]
    expect(body.meals[0]).toMatchObject({name:'午餐店',schedule_mode:'manual',insert_after:'C'})
    expect(body.locked_attraction_names).toEqual(['B']);expect(body.removed_attraction_names).toEqual(['X'])
    expect((w.get('[aria-label="午餐店用餐顺序"]').element as HTMLSelectElement).value).toBe('')
    w.unmount()
  })
  it('focuses the transport date and returns to the same segment after sync',async()=>{
    navigation.query={multi:'mc_test',stop:'hangzhou',revision:'3',basis:'city-basis',date:'2026-10-21',returnSection:'transport',edge:'1'}
    const data=draft();data.days.push({...data.days[0]!,day_index:1,date:'2026-10-21'});data.days_detail.push({...data.days_detail[0]!})
    vi.mocked(getDraft).mockResolvedValue(data);vi.mocked(multiApi).mockResolvedValue({id:'mc_test'})
    const wrapper=await openDraft()
    const cards=wrapper.findAllComponents({name:'DayCard'})
    expect(cards[0]!.props('isDefaultExpanded')).toBe(false);expect(cards[1]!.props('isDefaultExpanded')).toBe(true)
    await wrapper.findAll('button').find(b=>b.text().includes('同步并返回整趟旅行'))!.trigger('click');await flushPromises()
    expect(navigation.push).toHaveBeenCalledWith({path:'/multi-trip/mc_test',query:{city:'hangzhou',section:'transport',edge:'1'}})
    wrapper.unmount()
  })
  it('syncs from the bottom action and returns to the city just edited',async()=>{
    navigation.query={multi:'mc_test',stop:'hangzhou',revision:'3',basis:'city-basis'}
    vi.mocked(multiApi).mockResolvedValue({id:'mc_test'})
    const wrapper=await openDraft()
    const sync=wrapper.findAll('button').find(b=>b.text().includes('同步并返回整趟旅行'))!
    await sync.trigger('click');await flushPromises()
    expect(multiApi).toHaveBeenCalledWith('/mc_test/cities/hangzhou/import','post',{revision:3,basis:'city-basis',draft_id:'draft-test'})
    expect(navigation.push).toHaveBeenCalledWith({path:'/multi-trip/mc_test',query:{city:'hangzhou'}})
    wrapper.unmount()
  })
  it('recovers a finalized draft into its saved history after a lost completion event', async () => {
    vi.mocked(getDraft).mockResolvedValue({ ...draft(),status:'finalized',finalized_trip_id:42 })
    const wrapper=await openDraft()
    expect(navigation.replace).toHaveBeenCalledWith('/trip/42')
    expect(wrapper.findAll('button').some(b=>b.text().includes('定稿并保存'))).toBe(false)
    wrapper.unmount()
  })
  it('requires unlock before deletion and sends the unlocked state', async () => {
    const wrapper = await openDraft()
    expect(wrapper.get('[aria-label="删除 B"]').attributes('disabled')).toBeDefined()
    const updated = draft().days_detail[0]
    updated.locked_attraction_names = []
    vi.mocked(recomputeDay).mockResolvedValue({ day_detail: updated } as any)
    await wrapper.get('[aria-label="解锁 B"]').trigger('click')
    await flushPromises()
    expect(vi.mocked(recomputeDay).mock.calls[0][2].locked_attraction_names).toEqual([])
    expect(wrapper.get('[aria-label="删除 B"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('restores saved attractions after a failed deletion and permits retry', async () => {
    const wrapper = await openDraft()
    vi.mocked(recomputeDay).mockRejectedValueOnce(new Error('simulated failure'))
    await wrapper.get('[aria-label="删除 C"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="删除 C"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="恢复 C"]').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('本次修改尚未保存')
    const saved = draft().days_detail[0]
    saved.attractions = saved.attractions.filter(a => a.name !== 'C')
    saved.removed_attraction_names = ['C']
    vi.mocked(recomputeDay).mockResolvedValueOnce({ day_detail: saved } as any)
    await wrapper.get('[aria-label="删除 C"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="恢复 C"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('restores lock and start time when their recomputation fails', async () => {
    const wrapper = await openDraft()
    vi.mocked(recomputeDay).mockRejectedValue(new Error('simulated failure'))
    await wrapper.get('[aria-label="解锁 B"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="解锁 B"]').exists()).toBe(true)
    await wrapper.get('input.day-start-input').setValue('11:30')
    await flushPromises()
    expect((wrapper.get('input.day-start-input').element as HTMLInputElement).value).toBe('09:00')
    wrapper.unmount()
  })

  it('normalizes drag order around a lock and rolls back on failure', async () => {
    const wrapper = await openDraft()
    vi.mocked(recomputeDay).mockRejectedValue(new Error('simulated failure'))
    const drag = wrapper.getComponent({ name: 'Draggable' })
    drag.vm.$emit('update:modelValue', ['D', 'C', 'B', 'A'].map(name => ({ name })))
    drag.vm.$emit('end')
    await flushPromises()
    expect(vi.mocked(recomputeDay).mock.calls[0][2].attractions_order).toEqual(['D', 'B', 'C', 'A'])
    expect(wrapper.findAll('.attr-row .name').map(e => e.text())).toEqual(['A', 'B', 'C', 'D'])
    wrapper.unmount()
  })

  it('keeps the saved day after AI failure and prevents finalize while saving', async () => {
    const wrapper = await openDraft()
    let rejectSave!: (error: Error) => void
    vi.mocked(aiRearrangeDay).mockImplementation(() => new Promise((_, reject) => { rejectSave = reject }))
    await wrapper.findAll('button').find(b => b.text() === 'AI 重新安排')!.trigger('click')
    await flushPromises()
    const dialog = document.querySelector('[role="dialog"]')!
    const hint = dialog.querySelector('textarea')!
    hint.value = '调整未锁定景点'
    hint.dispatchEvent(new Event('input', { bubbles: true }))
    const confirm = [...dialog.querySelectorAll('button')].find(b => b.textContent?.replace(/\s/g, '') === '重新安排')!
    confirm.click()
    await flushPromises()
    expect(wrapper.findAll('button').find(b => b.text() === '定稿并保存')!.attributes('disabled')).toBeDefined()
    rejectSave(new Error('simulated AI failure'))
    await flushPromises()
    expect(wrapper.findAll('.attr-row .name').map(e => e.text())).toEqual(['A', 'B', 'C', 'D'])
    expect(wrapper.get('[role="alert"]').text()).toContain('本次修改尚未保存')
    expect(wrapper.findAll('button').find(b => b.text() === '定稿并保存')!.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('explicitly restores deleted attractions and preserves the meal anchor', async () => {
    const data = draft()
    data.days_detail[0].attractions = data.days_detail[0].attractions.filter(a => a.name !== 'C')
    data.days_detail[0].removed_attraction_names = ['C']
    Object.assign(data.days_detail[0], {
      meals: [{ name: '午餐', category: 'main' }],
      timeline_order: [{ kind: 'attraction', ref_name: 'B' }, { kind: 'meal', ref_name: '午餐' }],
    })
    vi.mocked(getDraft).mockResolvedValue(data)
    vi.mocked(recomputeDay).mockResolvedValue({ day_detail: draft().days_detail[0] } as any)
    const wrapper = await openDraft()
    await wrapper.get('[aria-label="恢复 C"]').trigger('click')
    await flushPromises()
    const edit = vi.mocked(recomputeDay).mock.calls[0][2]
    expect(edit.attractions_order).toEqual(['A', 'B', 'D', 'C'])
    expect(edit.removed_attraction_names).toEqual([])
    expect(edit.meals![0].insert_after).toBe('B')
    wrapper.unmount()
  })

  it('removing one meal keeps the remaining meals in their saved positions', async () => {
    const data = draft()
    Object.assign(data.days_detail[0], {
      meals: [{ name: '早餐', category: 'main' }, { name: '午餐', category: 'main' }],
      timeline_order: [
        { kind: 'meal', ref_name: '早餐' }, { kind: 'attraction', ref_name: 'D' },
        { kind: 'meal', ref_name: '午餐' },
      ],
    })
    vi.mocked(getDraft).mockResolvedValue(data)
    vi.mocked(recomputeDay).mockResolvedValue({ day_detail: draft().days_detail[0] } as any)
    const wrapper = await openDraft()
    await wrapper.findAll('.meal-row')[0].get('button').trigger('click')
    await flushPromises()
    const edit = vi.mocked(recomputeDay).mock.calls[0][2]
    expect(edit.meals).toEqual([{ name: '午餐', category: 'main', insert_after: 'D' }])
    wrapper.unmount()
  })
})

describe('current itinerary descriptions', () => {
  it('hides legacy prose and shows only the successful saved description as plain text', async () => {
    const initial=draft()
    Object.assign(initial.days_detail[0],{description:'旧叙述：先游已删除景点，已预约成功'})
    vi.mocked(getDraft).mockResolvedValue(initial)
    const wrapper=await openDraft()
    expect(wrapper.text()).not.toContain('已预约成功')
    expect(wrapper.text()).toContain('旧版说明尚未核对')
    const saved=draft().days_detail[0]
    Object.assign(saved,{description:'10:15开始，游览：<img src=x onerror=alert(1)>',description_source:'itinerary_facts_v1',day_start_time:'10:15'})
    vi.mocked(recomputeDay).mockResolvedValue({day_detail:saved} as any)
    await wrapper.get('input.day-start-input').setValue('10:15');await flushPromises()
    expect(wrapper.get('.description-text').text()).toContain('10:15开始')
    expect(wrapper.get('.description-text').text()).toContain('<img')
    expect(wrapper.find('.description-text img').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('旧版说明尚未核对')
    wrapper.unmount()
  })
  it('keeps the last saved explanation when a changed time fails to save', async () => {
    const initial=draft()
    Object.assign(initial.days_detail[0],{description:'09:00开始，游览：C',description_source:'itinerary_facts_v1'})
    vi.mocked(getDraft).mockResolvedValue(initial)
    const wrapper=await openDraft()
    vi.mocked(recomputeDay).mockRejectedValue(new Error('route unavailable'))
    await wrapper.get('input.day-start-input').setValue('11:30');await flushPromises()
    expect(wrapper.get('.description-text').text()).toContain('09:00开始')
    expect(wrapper.get('.description-text').text()).not.toContain('11:30')
    expect(wrapper.get('[role="alert"]').text()).toContain('本次修改尚未保存')
    wrapper.unmount()
  })
  it('loads the newest saved description on 409 rather than restoring a superseded view', async () => {
    const wrapper=await openDraft()
    const newer=draft()
    Object.assign(newer.days_detail[0],{description:'12:00开始，游览：D',description_source:'itinerary_facts_v1',day_start_time:'12:00'})
    newer.days_detail[0].attractions=newer.days_detail[0].attractions.filter(a=>a.name!=='C')
    newer.days_detail[0].removed_attraction_names=['C']
    vi.mocked(getDraft).mockResolvedValueOnce(newer)
    vi.mocked(recomputeDay).mockRejectedValue({response:{status:409,data:{detail:'该天安排已被更新'}}})
    await wrapper.get('input.day-start-input').setValue('11:30');await flushPromises()
    expect(wrapper.get('.description-text').text()).toContain('12:00开始')
    expect(wrapper.find('[aria-label="恢复 C"]').exists()).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('已加载最新保存内容')
    expect((wrapper.get('input.day-start-input').element as HTMLInputElement).value).toBe('12:00')
    wrapper.unmount()
  })
  it('blocks another save if a conflict cannot reload the latest draft', async () => {
    const wrapper=await openDraft()
    vi.mocked(getDraft).mockRejectedValueOnce(new Error('offline'))
    vi.mocked(recomputeDay).mockRejectedValue({response:{status:409,data:{detail:'changed'}}})
    await wrapper.get('input.day-start-input').setValue('11:30');await flushPromises()
    expect(wrapper.text()).toContain('最新草稿读取失败')
    expect(wrapper.findAll('button').some(b=>b.text()==='定稿并保存')).toBe(false)
    expect(wrapper.find('[aria-label="删除 C"]').exists()).toBe(false)
    expect(recomputeDay).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})

describe('meal intent recovery',()=>{
  it('shows an AI omission recovery while keeping the saved dinner visible',async()=>{
    const data=draft()
    Object.assign(data.days_detail[0],{meals:[{name:'Dinner',type:'dinner',category:'main'}],meal_adjustments:[]})
    vi.mocked(getDraft).mockResolvedValue(data)
    const wrapper=await openDraft()
    const updated={...data.days_detail[0],meal_adjustments:['AI未完整安排晚餐，已保留Dinner。'],description_source:'itinerary_facts_v1',description:'17:30–18:30 晚餐：Dinner'}
    vi.mocked(aiRearrangeDay).mockResolvedValue({day_detail:updated} as any)
    wrapper.getComponent({name:'DayCard'}).vm.$emit('ai-rearrange','优化路线')
    await flushPromises()
    expect(wrapper.findAll('.meal-row .meal-name').map(e=>e.text())).toEqual(['Dinner'])
    expect(wrapper.get('[role="status"]').text()).toContain('已保留Dinner')
    expect(wrapper.get('.description-text').text()).toContain('晚餐：Dinner')
    wrapper.unmount()
  })
  it('shows a deletion adjustment and removes it after the user explicitly deletes the meal',async()=>{
    const data=draft()
    Object.assign(data.days_detail[0],{meals:[{name:'Lunch',type:'lunch',category:'main'}],meal_adjustments:['原景点已删除，Lunch保留在首个景点之前。'],description_source:'itinerary_facts_v1',description:'11:30–12:30 午餐：Lunch'})
    vi.mocked(getDraft).mockResolvedValue(data)
    const wrapper=await openDraft()
    expect(wrapper.get('[role="status"]').text()).toContain('首个景点之前')
    const updated={...data.days_detail[0],meals:[],meal_adjustments:[],description:'当前未安排午餐'}
    vi.mocked(recomputeDay).mockResolvedValue({day_detail:updated} as any)
    await wrapper.get('.meal-row button').trigger('click');await flushPromises()
    expect(vi.mocked(recomputeDay).mock.calls[0][2].meals).toEqual([])
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('.description-text').text()).not.toContain('11:30–12:30')
    wrapper.unmount()
  })
})


describe('dining changes preserve saved facts',()=>{
 it('refreshes alternatives without changing saved meals',async()=>{
  const data=draft();Object.assign(data.days_detail[0],{meals:[{name:'原店',type:'lunch'}]})
  vi.mocked(getDraft).mockResolvedValue(data)
  vi.mocked(refreshDiningOptions).mockResolvedValue({dining_pool:{main:[{name:'新店',category:'main'}]},message:'备选已更新'})
  const w=await openDraft();w.getComponent({name:'DayCard'}).vm.$emit('refresh-dining');await flushPromises()
  expect(refreshDiningOptions).toHaveBeenCalledWith('draft-test',0)
  expect(w.getComponent({name:'DayCard'}).props('context').dining_pool.main[0].name).toBe('新店')
  expect(w.getComponent({name:'DayCard'}).props('detail').meals[0].name).toBe('原店')
  expect(recomputeDay).not.toHaveBeenCalled();w.unmount()
 })
 it('keeps previous candidates when refresh fails',async()=>{
  const data=draft();data.days[0].dining_pool={main:[{name:'原备选'}]}
  vi.mocked(getDraft).mockResolvedValue(data);vi.mocked(refreshDiningOptions).mockRejectedValue(new Error('offline'))
  const w=await openDraft();w.getComponent({name:'DayCard'}).vm.$emit('refresh-dining');await flushPromises()
  expect(w.getComponent({name:'DayCard'}).props('context').dining_pool.main[0].name).toBe('原备选')
  expect(w.text()).toContain('尚未保存');w.unmount()
 })
 it('rolls back a failed restaurant replacement and sends its slot and anchor',async()=>{
  const data=draft();Object.assign(data.days_detail[0],{meals:[{name:'原店',type:'lunch',category:'main',schedule_mode:'manual'}],timeline_order:[{kind:'meal',ref_name:'原店'}]})
  vi.mocked(getDraft).mockResolvedValue(data);vi.mocked(recomputeDay).mockRejectedValue(new Error('route failed'))
  const w=await openDraft();const chooser=w.findAllComponents({name:'AddDiningPopover'}).find(c=>c.props('replaceName')==='原店')!
  chooser.vm.$emit('add',{name:'新店',type:'lunch',category:'main',schedule_mode:'manual',preferred_slot:'lunch',insert_after:'B',avg_cost:40})
  await flushPromises()
  expect(vi.mocked(recomputeDay).mock.calls[0][2].meals?.[0]).toMatchObject({name:'新店',preferred_slot:'lunch',insert_after:'B'})
  expect(w.getComponent({name:'DayCard'}).props('detail').meals[0].name).toBe('原店');w.unmount()
 })
})


it('adopts a later suggestion only on click and keeps locks, removals and manual meals in the edit',async()=>{
 const d=draft();Object.assign(d.days_detail[0],{schedule_suggestion:{day_start_time:'10:30',saved_minutes:90,message:'减少90分钟空档'},removed_attraction_names:['已删除'],timeline_order:[{kind:'attraction',ref_name:'B'},{kind:'meal',ref_name:'午餐'}],meals:[{name:'午餐',type:'lunch',category:'main',insert_after:'B',schedule_mode:'manual'}]})
 vi.mocked(getDraft).mockResolvedValue(d)
 const w=await openDraft()
 expect(recomputeDay).not.toHaveBeenCalled()
 vi.mocked(recomputeDay).mockResolvedValue({day_detail:{...d.days_detail[0],day_start_time:'10:30'}} as any)
 await w.findAll('button').find(b=>b.text()==='采用较晚出发时间')!.trigger('click');await flushPromises()
 expect(vi.mocked(recomputeDay).mock.calls[0][2]).toMatchObject({day_start_time:'10:30',locked_attraction_names:['B'],removed_attraction_names:['已删除'],meals:[{name:'午餐',insert_after:'B',schedule_mode:'manual'}]})
 w.unmount()
})

it('requires preview confirmation for transport, invalidates preview on edits, and blocks finalization while dirty',async()=>{
 const w=await openDraft()
 const {default:JourneyEditor}=await import('@/components/JourneyEditor.vue')
 w.findAllComponents(JourneyEditor).at(-1)!.vm.$emit('update:modelValue',{origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'})
 await flushPromises()
 expect(w.findAll('button').some(b=>b.text().includes('定稿并保存'))).toBe(false)
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'preview',notice:'原安排保留',intercity_total:0,impacts:[]})
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls[0]).toEqual(['draft-test',{origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'},undefined,true,undefined])
 const edited={origin_city:'南京',return_city:'南京',destination_timezone:'Asia/Shanghai'}
 w.findAllComponents(JourneyEditor).at(-1)!.vm.$emit('update:modelValue',edited);await flushPromises()
 expect(w.findAll('button').some(b=>b.text().startsWith('确认并保存'))).toBe(false)
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 await w.findAll('button').find(b=>b.text().startsWith('确认并保存'))!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',edited,'preview',true,undefined])
 w.unmount()
})


it('shows unsaved ticket edits without reusing the old available-time summary',async()=>{
 const w=await openDraft()
 const {default:JourneyEditor}=await import('@/components/JourneyEditor.vue')
 const next={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai',outbound:{mode:'train',service_number:'G99',departure_time:'2026-10-20T09:00',arrival_time:'2026-10-20T15:00',departure_station:'上海虹桥',arrival_station:'北京南',passengers:1,ticket_total:null}}
 w.findAllComponents(JourneyEditor).at(-1)!.vm.$emit('update:modelValue',next);await flushPromises()
 expect(w.get('.transport-overview').text()).toContain('G99')
 expect(w.get('.transport-overview').text()).toContain('预览后再更新可游玩时间')
 expect(w.find('.transport-overview .day-windows').exists()).toBe(false)
 expect(changeJourney).not.toHaveBeenCalled();expect(adjustJourney).not.toHaveBeenCalled()
 w.unmount()
})

it('coordinates a chosen alternative with both days and waits for explicit confirmation',async()=>{
 const w=await openDraft()
 const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'whole',preview_token:'selected',notice:'保留全部活动',intercity_total:240,budget:{total:500},impacts:[{date:'2026-10-20',window:{start_minutes:600,end_minutes:1320,notes:[],unknown_cost_items:[],overnight_stay:true},changes:['市内出发从08:00调整到10:00'],conflicts:[]}]})
 w.findComponent(JourneyComparison).vm.$emit('choose',journey);await flushPromises()
 expect(adjustJourney).toHaveBeenCalledWith('draft-test',{journey,coordinate_trip:true,ticket_basis:undefined})
 expect(w.get('.travel-preview').text()).toContain('市内出发从08:00调整到10:00')
 expect(w.get('.transport-desk .travel-preview').isVisible()).toBe(true)
 expect(getDraft).toHaveBeenCalledTimes(1)
 await w.get('.proposal-ack input').setValue(true)
 await w.findAll('button').find(b=>b.text().startsWith('确认并保存'))!.trigger('click');await flushPromises()
 expect(adjustJourney).toHaveBeenLastCalledWith('draft-test',expect.objectContaining({journey,coordinate_trip:true,adjustment_id:'whole',preview_token:'selected',acknowledge_adjustments:true}))
 w.unmount()
})

it('invalidates a synchronization preview when the user changes the synchronization choice',async()=>{
 const w=await openDraft()
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'sync',notice:'预览',intercity_total:0,impacts:[]})
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(true)
 await w.findAll('input[type="checkbox"]').find(input=>input.element.parentElement?.textContent?.includes('同步可容纳'))!.setValue(false);await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(false)
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',null,undefined,false,undefined])
 await w.get('.proposal-buttons .secondary-action').trigger('click');await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(false)
 expect(vi.mocked(changeJourney).mock.calls).toHaveLength(2)
 w.unmount()
})

it('carries the recommendation basis into both preview and confirmation and clears it on cancellation',async()=>{
 const w=await openDraft();const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'basis-check',preview_token:'verified',notice:'核对',intercity_total:0,impacts:[]})
 w.findComponent(JourneyComparison).vm.$emit('choose',journey,'saved-basis');await flushPromises()
 expect(adjustJourney).toHaveBeenLastCalledWith('draft-test',expect.objectContaining({journey,coordinate_trip:true,ticket_basis:'saved-basis'}))
 await w.get('.proposal-ack input').setValue(true)
 await w.findAll('button').find(b=>b.text().startsWith('确认并保存'))!.trigger('click');await flushPromises()
 expect(adjustJourney).toHaveBeenLastCalledWith('draft-test',expect.objectContaining({journey,coordinate_trip:true,preview_token:'verified',ticket_basis:'saved-basis',acknowledge_adjustments:true}))
 w.findComponent(JourneyComparison).vm.$emit('choose',journey,'another-basis');await flushPromises()
 await w.get('.proposal-buttons .secondary-action').trigger('click');await flushPromises()
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'basic',impacts:[]})
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)![4]).toBeUndefined();w.unmount()
})


it('treats movable clocks separately from ordering locks and restores failed optional changes',async()=>{
 vi.mocked(recomputeDay).mockRejectedValue(new Error('route unavailable'))
 const w=await openDraft()
 expect(w.text()).toContain('旧安排未声明时刻是否可移')
 const checkbox=w.get('.time-constraints input[type=checkbox]')
 await checkbox.setValue(true);await flushPromises()
 const body:any=vi.mocked(recomputeDay).mock.calls[0][2]
 expect(body.time_constraints).toMatchObject({allow_start_shift:true,fixed_start_time:null,appointments:[]})
 expect(body.locked_attraction_names).toEqual(['B'])
 expect((w.get('.time-constraints input[type=checkbox]').element as HTMLInputElement).checked).toBe(false)
 w.unmount()
})

it('requires review of the transport-first proposal before atomic confirmation',async()=>{
 const w=await openDraft();const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'proposal',preview_token:'token',notice:'需要核对',changes:['A移至第二天','午餐移除，核对在途用餐'],impacts:[],days_detail:[],unassigned_attractions:[{id:'a',name:'A'}],intercity_total:0})
 w.findComponent(JourneyComparison).vm.$emit('adjust',journey,'basis');await flushPromises()
 expect(adjustJourney).toHaveBeenCalledWith('draft-test',{journey,ticket_basis:'basis',coordinate_trip:true})
 expect(w.get('.travel-preview').text()).toContain('A移至第二天')
 const save=w.findAll('button').find(b=>b.text().startsWith('确认并保存'))!
 expect(save.attributes('disabled')).toBeDefined()
 await w.get('.travel-preview input[type="checkbox"]').setValue(true)
 await save.trigger('click');await flushPromises()
 expect(vi.mocked(adjustJourney).mock.calls[1]).toEqual(['draft-test',{journey,ticket_basis:'basis',coordinate_trip:true,adjustment_id:'proposal',preview_token:'token',acknowledge_adjustments:true}])
 expect(changeJourney).not.toHaveBeenCalled();w.unmount()
})

it('always coordinates ticket adoption instead of accepting a merely conflict-free schedule',async()=>{
 const w=await openDraft();const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'conflict',impacts:[{date:'2026-10-20',window:{notes:[]},conflicts:['景点与到达冲突']} ]})
 vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'joint',preview_token:'joint-token',changes:['A移至次日'],impacts:[],days_detail:[],unassigned_attractions:[],intercity_total:0})
 w.findComponent(JourneyComparison).vm.$emit('choose',journey,'basis');await flushPromises()
 expect(adjustJourney).toHaveBeenCalledWith('draft-test',{journey,ticket_basis:'basis',coordinate_trip:true})
 expect(w.get('.travel-preview').text()).toContain('A移至次日')
 expect(w.findAll('button').find(b=>b.text().startsWith('确认并保存'))!.attributes('disabled')).toBeDefined()
 expect(changeJourney).not.toHaveBeenCalled()
 w.unmount()
})

it('starts a new journey with a coordinated preview and keeps the original draft until confirmation',async()=>{
 const data:any=draft();data.days_detail=[null];data.request.journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(getDraft).mockResolvedValue(data)
 vi.mocked(assembleDay).mockRejectedValue({response:{status:409,data:{detail:'与交通或休息安排冲突，本次修改未保存：营业时间'}}})
 vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'initial-fit',preview_token:'p',changes:['A移至第二天'],impacts:[],days_detail:[],unassigned_attractions:[],intercity_total:0})
 const w=await openDraft()
 expect(adjustJourney).toHaveBeenCalledWith('draft-test',{journey:data.request.journey,ticket_basis:undefined,coordinate_trip:true,assemble_pending:true,refill_meals:true})
 expect(assembleDay).not.toHaveBeenCalled()
 expect(w.get('.travel-preview').text()).toContain('A移至第二天')
 expect(w.text()).not.toContain('本次修改尚未保存')
 expect(w.findAll('button').find(b=>b.text().startsWith('确认并保存'))!.attributes('disabled')).toBeDefined()
 expect(data.days_detail).toEqual([null])
 w.unmount()
})

it('discards a late transport-first preview after local traffic input changes',async()=>{
 let resolve:any;vi.mocked(adjustJourney).mockReturnValue(new Promise(r=>resolve=r))
 const w=await openDraft();const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const {default:JourneyEditor}=await import('@/components/JourneyEditor.vue')
 w.findComponent(JourneyComparison).vm.$emit('adjust',{origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'});await flushPromises()
 w.findAllComponents(JourneyEditor).at(-1)!.vm.$emit('update:modelValue',{origin_city:'南京',return_city:'南京',destination_timezone:'Asia/Shanghai'});await flushPromises()
 resolve({adjustment_id:'late',impacts:[],changes:[]});await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(false);expect(w.text()).toContain('旧预览未采用');w.unmount()
})

it('keeps pending attractions visible and blocks finalization until they are placed or explicitly dropped',async()=>{
 const value:any=draft();value.unassigned_attractions=[{id:'pending',name:'远处景点',reason:'交通后未分配'}]
 vi.mocked(getDraft).mockResolvedValue(value)
 vi.mocked(adjustJourney).mockResolvedValue({adjustment_id:'drop',preview_token:'drop-token',impacts:[],changes:['明确不再安排远处景点'],days_detail:[],unassigned_attractions:[],intercity_total:0})
 const w=await openDraft()
 expect(w.get('[aria-label="待安排景点"]').text()).toContain('远处景点')
 expect(w.findAll('button').find(b=>b.text()==='定稿并保存')!.attributes('disabled')).toBeDefined()
 await w.findAll('button').find(b=>b.text()==='不再安排，预览')!.trigger('click');await flushPromises()
 expect(adjustJourney).toHaveBeenCalledWith('draft-test',{journey:null,ticket_basis:undefined,discard_ids:['pending']})
 expect(w.get('.travel-preview').text()).toContain('明确不再安排远处景点');w.unmount()
})
