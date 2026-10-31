export type Counts = { P: number; F: number; E: number; U: number; NA: number; applicable: number }
export type Summary = {
  planned: number; completed: number; unique_cases: number; not_applicable: number; incomplete: number
  real_requests: number; real_model_runs: number; technical_errors: number; fallback: number
  finding_runs: number; finding_cases: number; injected_runs: number; categories: Record<string, number>
  tokens: number; usage_known_runs: number; cost_usd: number | null; cost_known_runs: number; peak_cost_usd: number | null
  wall_p50: number | null; wall_p95: number | null; wall_count: number; p95_small_sample: boolean
  pending_cases: number; metrics: Record<string, Counts>; diagnostic_counts: Counts
  outcome_pass: number; outcome_applicable: number; outcome_scope: string
}
export type Check = { rule_id: string; layer: string; status: string; expected: unknown; actual: unknown; reason: string; category: string | null; triage_note: string | null; evidence_paths: string[] }
export type Experiment = {
  experiment_id: string; title: string; created_at: string; published_at: string; plan_sha256: string
  source_sha256: string; dataset_sha256: string; evaluator_versions: string[]; case_versions: string[]
  model: { name: string; temperature: number; thinking: string }; limitations: string[]
  pricing: { basis: string; source_url: string | null; checked_on: string | null; budget_usd: number | null; input_tokens: number | null; output_tokens: number | null; cache_read_tokens: number | null }
  variants?: { variant: string; summary: Summary }[]
}
export type Run = {
  run_id: string; case_id: string; title: string; variant: string; repetition: number; target: string; split: string
  data_origin: string; provenance: string; case_version: string; reference_status: string; execution_state: string
  operation_status: string | null; business_outcome: string | null; started_at: string | null; wall_seconds: number | null
  usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null
  actual_requests: number; cost_usd: number | null; peak_cost_usd: number | null; categories: string[]; trace_status: string
  counts: Counts
}
export type Span = { id: string; parent_id: string | null; name: string; run_type: string; start_time: string; end_time: string; status: string; milliseconds: number; facts: unknown }
export type RunDetail = Run & { checks: Check[]; experiment: Experiment; detail: {
  inputs: Record<string, unknown>; before: unknown; latest: unknown; after: unknown; raw_model: unknown; final_output: Record<string, unknown> | null
  candidate_checks: { candidate_id: string; eligible: boolean; reasons: string[]; margins: unknown; tight: boolean }[] | null
  sources: unknown; annotation: unknown; http_status: number | null; checkpoint_statuses: unknown
  trace: { operation_id: string | null; session_alias: string | null; spans: Span[]; status: string; cloud_status: string; langsmith_url: string | null }
} }
export type RunPage = { items: Run[]; total: number; next_cursor: string | null; summary: Summary; snapshot_at: string; experiment: Experiment }
export type QualityStatus = { enabled: boolean; state: string; snapshot_at: string | null; message?: string; invalid_reports?: number }
export type Comparison = { compatible: boolean; formal_delta: null; pairing: string; comparable_pairs: number; missing_pairs: number; left_summary: Summary; right_summary: Summary; pairs: { case_id: string; repetition: number; left: string | null; right: string | null; comparable: boolean; reason: string | null; changes: { rule_id: string; layer: string; left: string | null; right: string | null; change: string }[] }[] }
const cache = new Map<string, { value: unknown; at: string }>()
export class QualityError extends Error { constructor(message: string, public status: number) { super(message) } }
export async function qualityGet<T>(path: string): Promise<{ data: T; stale: boolean; cachedAt: string }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 12000)
  try {
    const response = await fetch(`/api/quality${path}`, { signal: controller.signal, cache: 'no-store' })
    if (!response.ok) {
      if ([403, 404, 422].includes(response.status)) { cache.delete(path); throw new QualityError(response.status === 403 ? '质量工作台已关闭' : '记录不存在、筛选或分页已过期，请刷新。', response.status) }
      throw new Error('读取质量报告失败')
    }
    const value: T = await response.json()
    const at = new Date().toISOString()
    if (path === '/status' && !(value as QualityStatus).enabled) cache.clear()
    cache.set(path, { value, at })
    if (cache.size > 40) cache.delete(cache.keys().next().value!)
    return { data: value, stale: false, cachedAt: at }
  } catch (error) {
    if (error instanceof QualityError) throw error
    const previous = cache.get(path)
    if (previous) return { data: previous.value as T, stale: true, cachedAt: previous.at }
    throw new QualityError('无法连接质量工作台，当前页面没有可用缓存。', 0)
  } finally { clearTimeout(timer) }
}
export const qualityLabels: Record<string, string> = {
  model_issue: '模型问题 · 待人审', reference_dispute: '参考口径分歧', evidence_gap: '证据缺项', fault_injection: '故障注入', unclassified: '待分类诊断',
  synthetic: '人工构造 · 未经人审', mixed_historical_itinerary_and_new_capture: '历史日程 + 补采票务', mixed_historical_day_and_new_route_capture: '历史日程 + 补采路线',
  baseline: '规则 / 保留原安排', current_live: '真实模型方案', current_replay: '模型替身回放',
  live_model_with_replay: '真实模型 + 事实回放', injected_failure: '故障注入', no_model: '无需模型',
  ticket_recommendation: '票务推荐', day_rearrangement: '每日 AI 重排',
  success: '技术执行完成', error: '技术错误', timeout: '超时', conflict: '冲突拒绝', cancelled: '已取消', rejected: '拒绝保存',
  recommended: '已推荐', adjusted: '已处理重排', fallback: '规则回退', preserved_original: '保留原安排', empty_unavailable: '无可用票', empty_conflict: '候选全部冲突',
  NOT_APPLICABLE: '不适用', NOT_RUN: '未运行', COMPLETED: '执行完成', pending_human: '待人工确认',
  PASS: '通过', FAIL: '失败', ERROR: '缺证据 / 评分错误', NOT_EVALUATED: '未评估',
  model: '原始模型', system: '系统结果', observability: '观测', judge: '辅助评分',
  injected_model: '故障注入模型 · 单列', system_constraints: '系统硬约束', model_raw: '模型原始遵循', task_quality: '任务质量',
  improved: '诊断改善', regressed: '诊断退步', unchanged: '不变', unknown: '无法判断',
}
export const label = (value: string | null | undefined) => value ? qualityLabels[value] || value : '未记录'
export const number = (value: number | null | undefined) => value == null ? '未记录' : value.toLocaleString('zh-CN')
export const usd = (value: number | null | undefined) => value == null ? '费用未知' : `US$${value.toFixed(6)}`
export const seconds = (value: number | null | undefined) => value == null ? '未记录' : `${value.toFixed(3)} s`
export const pretty = (value: unknown) => value == null ? '未记录' : JSON.stringify(value, null, 2)
export const when = (value: string | null | undefined) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未记录'
