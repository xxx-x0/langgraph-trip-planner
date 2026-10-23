import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Result from './Result.vue'
import { finalizeDraftStream, getTripDetail, saveTripToHistory } from '@/services/api'

const state = vi.hoisted(() => ({ route: { query: {} as Record<string,string>, params: {} as Record<string,string> } }))
vi.mock('vue-router', () => ({ useRoute: () => state.route, useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }))
vi.mock('@/services/api', () => ({ finalizeDraftStream: vi.fn(), getTripDetail: vi.fn(), saveTripToHistory: vi.fn() }))
vi.mock('@/composables/useTripLoader', () => ({ useTripLoader: () => ({ updateProgress: vi.fn(), markReady: vi.fn(), dismiss: vi.fn() }) }))

const plan = { city: '苏州', days: [{ attractions: [], transportation: '公共交通' }], weather_info: [] }
function openResult() {
  return mount(Result, { global: { stubs: {
    TabOverview: true, TabBudget: true, TabMap: true, TabItinerary: true, TabWeather: true,
    'a-result': { props:['title'], template:'<section>{{title}}<slot name="extra" /></section>' },
    'a-button': { template:'<button><slot /></button>' },
  } } })
}
beforeEach(() => {
  vi.resetAllMocks()
  state.route.query = {}
  state.route.params = {}
  sessionStorage.clear()
})

describe('saved result identity', () => {
  it('shows stream failure and retries the same saved draft identity', async () => {
    state.route.query = { streaming: 'true', draft_id: 'draft-kept' }
    vi.mocked(finalizeDraftStream).mockRejectedValueOnce(new Error('响应流在完成前中断'))
      .mockImplementationOnce(async (_id, callback) => {
        callback({ type: 'complete', trip_id: 42, trip_plan: plan } as any)
      })
    const wrapper=openResult()
    await flushPromises()
    expect(wrapper.text()).toContain('中断')
    const retry=wrapper.findAll('button').find(b=>b.text()==='重试')!
    await retry.trigger('click');await flushPromises()
    expect(vi.mocked(finalizeDraftStream).mock.calls.map(c=>c[0])).toEqual(['draft-kept','draft-kept'])
    expect(wrapper.text()).toContain('已保存')
    expect(saveTripToHistory).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('marks a finalized SSE result as saved and prevents duplicate history saves', async () => {
    state.route.query = { streaming: 'true', draft_id: 'draft-1' }
    vi.mocked(finalizeDraftStream).mockImplementation(async (_id, callback) => {
      callback({ type: 'complete', trip_id: 42, trip_plan: plan } as any)
    })
    const wrapper = openResult()
    await flushPromises()
    const button = wrapper.findAll('button').find(b => b.text().includes('已保存'))!
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    expect(saveTripToHistory).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('公共交通')
    expect(wrapper.findAll('button').some(b => b.text().includes('编辑'))).toBe(false)
    wrapper.unmount()
  })

  it('reopened history remains saved and cannot create another record by clicking save', async () => {
    state.route.params = { id: '42' }
    vi.mocked(getTripDetail).mockResolvedValue({ data: { plan } } as any)
    const wrapper = openResult()
    await flushPromises()
    const button = wrapper.findAll('button').find(b => b.text().includes('已保存'))!
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    expect(saveTripToHistory).not.toHaveBeenCalled()
    expect(wrapper.findAll('button').some(b => b.text().includes('编辑'))).toBe(false)
    wrapper.unmount()
  })
})

it('keeps legacy session results read only so edits cannot bypass draft rules',async()=>{
  sessionStorage.setItem('tripPlan',JSON.stringify(plan))
  const wrapper=openResult();await flushPromises()
  expect(wrapper.findAll('button').some(b=>b.text().includes('编辑'))).toBe(false)
  wrapper.unmount()
})


it('ignores child edit events so saved attraction facts remain unchanged', async () => {
  const saved={...plan,days:[{attractions:[{name:'甲园',image_url:'https://example.invalid/saved.jpg'}],transportation:'步行'}]}
  sessionStorage.setItem('tripPlan',JSON.stringify(saved))
  const wrapper=openResult();await flushPromises()
  await wrapper.findAll('.tab-pill').find(b=>b.text().includes('每日行程'))!.trigger('click');await flushPromises()
  const child=wrapper.findComponent({name:'TabItinerary'})
  expect(child.props('editMode')).toBe(false)
  child.vm.$emit('deleteAttraction',0,0);child.vm.$emit('moveAttraction',0,0,'down')
  await flushPromises()
  expect(child.props('tripPlan').days[0].attractions).toEqual([{name:'甲园',image_url:'https://example.invalid/saved.jpg'}])
  expect(JSON.parse(sessionStorage.getItem('tripPlan')!).days[0].attractions).toEqual([{name:'甲园',image_url:'https://example.invalid/saved.jpg'}])
  expect(saveTripToHistory).not.toHaveBeenCalled()
  wrapper.unmount()
})
