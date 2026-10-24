import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Antd from 'ant-design-vue'
import DraftView from './DraftView.vue'
import { getDraft, recomputeDay, aiRearrangeDay, refreshDiningOptions, changeJourney, multiApi } from '@/services/api'

const navigation = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), query: {} as Record<string,string> }))

vi.mock('@/services/api', () => ({
  multiApi:vi.fn(), changeJourney:vi.fn(), getDraft: vi.fn(), recomputeDay: vi.fn(), aiRearrangeDay: vi.fn(),
  assembleDay: vi.fn(), rewriteNarrative: vi.fn(), refreshDiningOptions: vi.fn(),
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

describe('saved draft edit protection', () => {
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
    await wrapper.get('input[type="time"]').setValue('11:30')
    await flushPromises()
    expect((wrapper.get('input[type="time"]').element as HTMLInputElement).value).toBe('09:00')
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

  it('loads the newest saved description on 409 rather than restoring a superseded view', async () => {
    const wrapper=await openDraft()
    const newer=draft()
    Object.assign(newer.days_detail[0],{description:'12:00开始，游览：D',description_source:'itinerary_facts_v1',day_start_time:'12:00'})
    newer.days_detail[0].attractions=newer.days_detail[0].attractions.filter(a=>a.name!=='C')
    newer.days_detail[0].removed_attraction_names=['C']
    vi.mocked(getDraft).mockResolvedValueOnce(newer)
    vi.mocked(recomputeDay).mockRejectedValue({response:{status:409,data:{detail:'该天安排已被更新'}}})
    await wrapper.get('input[type="time"]').setValue('11:30');await flushPromises()
    expect(wrapper.get('.narrative').text()).toContain('12:00开始')
    expect(wrapper.find('[aria-label="恢复 C"]').exists()).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('已加载最新保存内容')
    expect((wrapper.get('input[type="time"]').element as HTMLInputElement).value).toBe('12:00')
    wrapper.unmount()
  })

  it('blocks another save if a conflict cannot reload the latest draft', async () => {
    const wrapper=await openDraft()
    vi.mocked(getDraft).mockRejectedValueOnce(new Error('offline'))
    vi.mocked(recomputeDay).mockRejectedValue({response:{status:409,data:{detail:'changed'}}})
    await wrapper.get('input[type="time"]').setValue('11:30');await flushPromises()
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
    expect(wrapper.get('.narrative').text()).toContain('晚餐：Dinner')
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
    await wrapper.get('.meal-row .ant-btn-dangerous').trigger('click');await flushPromises()
    expect(vi.mocked(recomputeDay).mock.calls[0][2].meals).toEqual([])
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('.narrative').text()).not.toContain('11:30–12:30')
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
 expect(w.findAll('button').find(b=>b.text().includes('定稿并保存'))!.attributes('disabled')).toBeDefined()
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'preview',notice:'原安排保留',intercity_total:0,impacts:[]})
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls[0]).toEqual(['draft-test',{origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'},undefined,true,undefined])
 const edited={origin_city:'南京',return_city:'南京',destination_timezone:'Asia/Shanghai'}
 w.findAllComponents(JourneyEditor).at(-1)!.vm.$emit('update:modelValue',edited);await flushPromises()
 expect(w.findAll('button').some(b=>b.text()==='确认以上影响并保存交通')).toBe(false)
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 await w.findAll('button').find(b=>b.text()==='确认以上影响并保存交通')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',edited,'preview',true,undefined])
 w.unmount()
})


it('chooses an alternative into a synchronization preview and waits for explicit confirmation',async()=>{
 const w=await openDraft()
 const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'selected',notice:'保留全部活动',intercity_total:240,budget:{total:500},impacts:[{date:'2026-10-20',window:{start_minutes:600,end_minutes:1320},changes:['市内出发从08:00调整到10:00'],conflicts:[]}]})
 w.findComponent(JourneyComparison).vm.$emit('choose',journey);await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls).toEqual([['draft-test',journey,undefined,true,undefined]])
 expect(w.get('.travel-preview').text()).toContain('市内出发从08:00调整到10:00')
 expect(w.findAll('details.journey-change').some(d=>(d.element as HTMLDetailsElement).open && d.text().includes('编辑往返交通'))).toBe(true)
 expect(getDraft).toHaveBeenCalledTimes(1)
 await w.findAll('button').find(b=>b.text()==='确认以上影响并保存交通')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',journey,'selected',true,undefined])
 w.unmount()
})

it('invalidates a synchronization preview when the user changes the synchronization choice',async()=>{
 const w=await openDraft()
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'sync',notice:'预览',intercity_total:0,impacts:[]})
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(true)
 await w.get('details.journey-change input[type="checkbox"]').setValue(false);await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(false)
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',null,undefined,false,undefined])
 await w.findAll('button').find(b=>b.text()==='取消本次交通变更')!.trigger('click');await flushPromises()
 expect(w.find('.travel-preview').exists()).toBe(false)
 expect(vi.mocked(changeJourney).mock.calls).toHaveLength(2)
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

it('carries the recommendation basis into both preview and confirmation and clears it on cancellation',async()=>{
 const w=await openDraft();const {default:JourneyComparison}=await import('@/components/JourneyComparison.vue')
 const journey={origin_city:'上海',return_city:'上海',destination_timezone:'Asia/Shanghai'}
 vi.mocked(changeJourney).mockResolvedValue({preview_token:'verified',notice:'核对',intercity_total:0,impacts:[]})
 w.findComponent(JourneyComparison).vm.$emit('choose',journey,'saved-basis');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',journey,undefined,true,'saved-basis'])
 await w.findAll('button').find(b=>b.text()==='确认以上影响并保存交通')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)).toEqual(['draft-test',journey,'verified',true,'saved-basis'])
 w.findComponent(JourneyComparison).vm.$emit('choose',journey,'another-basis');await flushPromises()
 await w.findAll('button').find(b=>b.text()==='取消本次交通变更')!.trigger('click');await flushPromises()
 await w.findAll('button').find(b=>b.text()==='查看变更影响')!.trigger('click');await flushPromises()
 expect(vi.mocked(changeJourney).mock.calls.at(-1)![4]).toBeUndefined();w.unmount()
})
