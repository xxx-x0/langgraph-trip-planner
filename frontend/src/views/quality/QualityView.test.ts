import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, expect, it, vi } from 'vitest'
import QualityView from './QualityView.vue'
import QualityDetail from './QualityDetail.vue'
import QualityTrace from './QualityTrace.vue'
import type { RunDetail, Summary } from '@/services/quality'
const experiment = { experiment_id: 'eval_test', title: '真实诊断', created_at: '2026-10-24', published_at: '2026-10-25', model: { name: 'deepseek-v4-pro', temperature: .2, thinking: 'disabled' }, case_versions: ['1.0.1-draft'], evaluator_versions: ['rules-v1.1'], variants: [{variant:'baseline'}, {variant:'current_live'}], pricing: {}, limitations: ['参考待人工确认'] }
const counts = { P: 0, F: 1, E: 0, U: 0, NA: 0, applicable: 1 }
const summary = { planned:70, completed:70, unique_cases:30, not_applicable:0, incomplete:0, real_requests:60, real_model_runs:60, tokens:65660, usage_known_runs:60, cost_usd:.02273084, cost_known_runs:60, peak_cost_usd:.09609336, finding_runs:22, finding_cases:9, pending_cases:30, technical_errors:0, fallback:0, injected_runs:8, categories:{}, diagnostic_counts:counts, outcome_pass:30, outcome_applicable:30, outcome_scope:"T-OUTCOME", p95_small_sample:false, wall_count:60, wall_p50:1.5, wall_p95:2, metrics:{model_raw:counts} } as Summary
const row = { run_id:'current_live-R02-1',case_id:'R02',title:'锁定第二景点',variant:'current_live',repetition:1,target:'day_rearrangement',data_origin:'synthetic',provenance:'live_model_with_replay',operation_status:'success',business_outcome:'adjusted',categories:['model_issue'],counts,usage:{total_tokens:1604},cost_usd:.001,wall_seconds:2,trace_status:'local_only',reference_status:'pending_human',case_version:'v1',actual_requests:1 }
function api() {
  const mock = vi.fn(async (input: string) => {
    const url = new URL(input, 'http://test')
    if (url.pathname.endsWith('/status')) return Response.json({enabled:true,state:'ready'})
    if (url.pathname.endsWith('/experiments')) return Response.json({items:[experiment]})
    if (url.pathname.endsWith('/compare')) return Response.json({compatible:true,formal_delta:null,pairing:'case + repetition',comparable_pairs:22,missing_pairs:40,pairs:[]})
    if (url.pathname.endsWith('/runs')) return Response.json({items:[row],total:1,next_cursor:null,summary,snapshot_at:'2026-10-25',experiment})
    return Response.json({ ...row, experiment, checks:[], detail:{inputs:{hint:'C 尽量提前'},before:null,after:null,latest:null,raw_model:{attractions_order:['A','B','C']},final_output:null,sources:[],trace:{spans:[],status:'missing',cloud_status:'not_exported'},candidate_checks:null} })
  }); vi.stubGlobal('fetch', mock); return mock
}
afterEach(() => { vi.unstubAllGlobals() })
async function mounted(path: string) {
  const router = createRouter({history:createMemoryHistory(),routes:[{path:'/quality/runs',component:QualityView},{path:'/quality/experiments',component:QualityView},{path:'/quality/runs/:runId',component:QualityView}]})
  await router.push(path);await router.isReady()
  const wrapper = mount(QualityView,{global:{plugins:[router]}});await flushPromises();return {wrapper,router}
}
it('shows real usage, diagnostic-only scores, categories and query-preserving detail links', async () => {
  api();const {wrapper,router}=await mounted('/quality/runs?category=model_issue&variant=current_live')
  expect(wrapper.text()).toContain('65,660');expect(wrapper.text()).toContain('US$0.022731');expect(wrapper.text()).toContain('正式质量未评估')
  expect(wrapper.text()).toContain('模型问题');expect(wrapper.text()).toContain('技术完成 ≠ 需求完成')
  const link=wrapper.findAll('a').find(a=>a.attributes('href')?.includes('/runs/current_live-R02-1'))!
  await link.trigger('click');await flushPromises()
  expect(router.currentRoute.value.query.category).toBe('model_issue')
  expect(wrapper.text()).toContain('本批次未上传 LangSmith');wrapper.unmount()
})
it('filters via URL and resets old pagination, so refresh restores the same filter', async () => {
  const fetcher=api();const {wrapper,router}=await mounted('/quality/runs?cursor=old')
  const select=wrapper.findAll('select').find(s=>s.text().includes('参考口径分歧'))!
  await select.setValue('reference_dispute');await flushPromises()
  expect(router.currentRoute.value.query.category).toBe('reference_dispute');expect(router.currentRoute.value.query.cursor).toBeUndefined()
  expect(fetcher.mock.calls.some(([url])=>url.includes('category=reference_dispute'))).toBe(true);wrapper.unmount()
})
it('shows compatible diagnostic comparison without formal improvement claims', async () => {
  api();const {wrapper}=await mounted('/quality/experiments?experiment_id=eval_test')
  expect(wrapper.text()).toContain('可比较 22 对');expect(wrapper.text()).toContain('正式差值：未评估');wrapper.unmount()
})
it('renders disabled and empty states without fabricated statistics', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({enabled:false,state:'disabled'})))
  const {wrapper}=await mounted('/quality/runs');expect(wrapper.text()).toContain('质量工作台已关闭');expect(wrapper.find('.q-stats').exists()).toBe(false);wrapper.unmount()
  vi.stubGlobal('fetch',vi.fn(async (url:string)=>Response.json(url.endsWith('status')?{enabled:true,state:'empty'}:{items:[]})))
  const empty=await mounted('/quality/runs');expect(empty.wrapper.text()).toContain('尚无运行记录');empty.wrapper.unmount()
})
it('renders untrusted facts as text and identifies injected traces', () => {
  const attack='<img src=x onerror=alert(1)>'
  const detail={...row,provenance:'injected_failure',experiment,checks:[],detail:{inputs:{hint:attack},raw_model:{ids:[attack]},final_output:null,trace:{spans:[],cloud_status:'not_exported'},candidate_checks:null}} as unknown as RunDetail
  const wrapper=mount(QualityDetail,{props:{row:detail}})
  expect(wrapper.find('img').exists()).toBe(false);expect(wrapper.text()).toContain(attack);expect(wrapper.text()).toContain('原始错误不计真实模型质量');wrapper.unmount()
})
it('keeps parent and child timing separate with plain-text trace facts', () => {
  const trace={operation_id:'op',session_alias:'anon',status:'local_only',cloud_status:'not_exported',langsmith_url:null,spans:[{id:'root',parent_id:null,name:'day_rearrangement',milliseconds:2000,status:'success',facts:{},run_type:'chain',start_time:'2026-10-24',end_time:'2026-10-24'},{id:'child',parent_id:'root',name:'model_call',milliseconds:1800,status:'success',facts:{total_tokens:1604},run_type:'llm',start_time:'2026-10-24',end_time:'2026-10-24'}]}
  const wrapper=mount(QualityTrace,{props:{trace}});expect(wrapper.text()).toContain('不能相加');expect(wrapper.findAll('.q-span')).toHaveLength(2);expect(wrapper.text()).toContain('1604');wrapper.unmount()
})
