<template>
  <main class="quality-desk">
    <header class="q-hero"><div><p class="q-eyebrow">LET'S GO / QUALITY LAB</p><h1>质量工作台<span>让每一次判断，都有迹可循。</span></h1><p>票务推荐与每日重排 · 冻结实验 · 本机只读</p></div><div class="q-hero-status"><span class="q-dot"></span>{{ status?.enabled ? '本地报告' : '尚未启用' }}<small>云端状态未查询</small></div></header>
    <nav class="q-tabs" aria-label="质量工作台导航"><RouterLink :to="{ path: '/quality/runs', query: tabQuery }" :aria-current="mode !== 'experiments' ? 'page' : undefined">运行记录</RouterLink><RouterLink :to="{ path: '/quality/experiments', query: tabQuery }" :aria-current="mode === 'experiments' ? 'page' : undefined">评估实验</RouterLink><button @click="refresh" :disabled="loading">{{ loading ? '读取中…' : '刷新报告' }}</button></nav>
    <p v-if="stale" class="q-alert" role="status">连接暂不可用，正在显示截至 {{ when(cachedAt) }} 的内存缓存。筛选统计仅对应此缓存；未伪装成实时状态。</p>
    <p v-if="error" class="q-alert" role="alert">{{ error }}</p>
    <p v-if="status?.invalid_reports" class="q-alert">有 {{ status.invalid_reports }} 份发布报告不可读取，当前列表不包含这些报告。</p>
    <section v-if="status && !status.enabled" class="q-empty"><h2>质量工作台已关闭</h2><p>本机启动时设置 QUALITY_WORKBENCH_ENABLED=1，并导入脱敏报告后可查看。关闭状态不读取实验目录。</p></section>
    <section v-else-if="status?.enabled && !experiments.length && !loading" class="q-empty"><h2>尚无运行记录</h2><p>当前没有可读取的已发布报告。页面不会生成演示分数。</p></section>
    <template v-else-if="status?.enabled && experiments.length">
      <div class="q-notice"><b>诊断报告 · 正式质量未评估</b><span>待人工确认的参考不计正式成绩。模型问题、参考口径分歧、证据缺项与故障注入分别展示。</span></div>
      <div v-if="mode === 'detail'" class="q-section-head"><RouterLink :to="{ path: '/quality/runs', query: tabQuery }">← 返回筛选结果</RouterLink><RouterLink :to="{ path: '/quality/experiments', query: tabQuery }">查看实验比较 →</RouterLink></div>
      <QualityMetrics v-if="page && mode !== 'detail'" :s="page.summary" />
      <form v-if="mode !== 'detail'" class="q-filters" @submit.prevent="applySearch">
        <label class="q-wide">实验<select :value="selectedId" @change="change('experiment_id', $event)"><option v-for="e in experiments" :key="e.experiment_id" :value="e.experiment_id">{{ e.title }} · {{ when(e.created_at) }}</option></select></label>
        <label>方案<select :value="value('variant', 'current_live')" @change="change('variant', $event)"><option value="">全部方案</option><option v-for="v in selectedExperiment?.variants" :key="v.variant" :value="v.variant">{{ label(v.variant) }}</option></select></label>
        <label>诊断分类<select :value="value('category')" @change="change('category', $event)"><option value="">全部诊断</option><option v-for="c in categories" :key="c" :value="c">{{ label(c) }}</option></select></label>
        <details class="q-extra"><summary>更多筛选 · 操作、来源、性质、状态与日期</summary><div class="q-extra-grid">
        <label>操作<select :value="value('target')" @change="change('target', $event)"><option value="">全部链路</option><option value="ticket_recommendation">票务推荐</option><option value="day_rearrangement">每日 AI 重排</option></select></label>
        <label>来源<select :value="value('data_origin')" @change="change('data_origin', $event)"><option value="">全部来源</option><option value="synthetic">人工构造 · 未经人审</option><option value="mixed_historical_itinerary_and_new_capture">历史日程 + 补采票务</option><option value="mixed_historical_day_and_new_route_capture">历史日程 + 补采路线</option></select></label>
        <label>执行性质<select :value="value('provenance')" @change="change('provenance', $event)"><option value="">全部性质</option><option value="live_model_with_replay">真实模型 + 回放</option><option value="injected_failure">故障注入</option><option value="no_model">无需模型</option><option value="baseline">基线</option></select></label>

        <label>分组<select :value="value('split')" @change="change('split', $event)"><option value="">全部场景</option><option value="dev">dev · 20 场景</option><option value="holdout">holdout · 10 场景（待复核）</option></select></label>
        <label>技术状态<select :value="value('operation_status')" @change="change('operation_status', $event)"><option value="">全部状态</option><option v-for="s in ['success', 'error', 'timeout', 'cancelled', 'conflict', 'rejected']" :key="s" :value="s">{{ label(s) }}</option></select></label>
        <label>业务结果<select :value="value('business_outcome')" @change="change('business_outcome', $event)"><option value="">全部结果</option><option v-for="s in ['recommended', 'adjusted', 'fallback', 'preserved_original', 'empty_unavailable', 'empty_conflict', 'conflict', 'timeout', 'cancelled', 'rejected']" :key="s" :value="s">{{ label(s) }}</option></select></label>
        <label>开始日期<input type="date" :value="value('since')" @change="change('since', $event)"></label><label>结束日期<input type="date" :value="value('until')" @change="change('until', $event)"></label>
        <label>案例 / ID<input v-model="search" placeholder="例如 R02" aria-label="搜索案例"></label>
        </div></details>
        <div class="q-filter-actions"><label class="q-inline"><input type="checkbox" :checked="value('findings') === 'true'" @change="setQuery({ findings: ($event.target as HTMLInputElement).checked ? 'true' : '' })">仅失败 / 缺证据</label><button type="submit">搜索</button><button type="button" @click="router.push({ path: route.path, query: { experiment_id: selectedId, variant: 'current_live' } })">重置筛选</button></div>
      </form>
      <div v-if="loading" class="q-loading" role="status">正在读取冻结证据…</div>
      <section v-if="mode === 'detail' && detail && paired" class="q-panel"><h2>同案例证据对照 · 仅诊断</h2><p class="q-muted">{{ detail.case_id === paired.case_id && detail.repetition === paired.repetition ? '同案例 / 重复序号；输入与版本可比性以实验比较结果为准。' : '不是同案例重复配对，仅并列查看，不计算差值。' }}</p><div class="q-two"><div v-for="r in [paired, detail]" :key="r.run_id"><h3>{{ label(r.variant) }} · {{ r.run_id }}</h3><p>{{ label(r.business_outcome) }} · {{ usd(r.cost_usd) }}</p><h4>原始模型</h4><pre>{{ pretty(r.detail.raw_model) }}</pre><h4>最终结果</h4><pre>{{ pretty(r.detail.final_output) }}</pre><QualityChecks :checks="r.checks" /></div></div></section>
      <QualityDetail v-if="mode === 'detail' && detail" :key="detail.run_id" :row="detail" />
      <template v-else-if="page && mode !== 'detail'">
        <div class="q-section-head"><p class="q-muted">快照发布于 {{ when(page.snapshot_at) }} · 统计随当前筛选，含完整分母</p><a class="q-button" :href="`/api/quality/experiments/${selectedId}/export`">导出完整脱敏报告</a></div>
        <div v-if="mode === 'runs'" class="q-panel">
          <div class="q-section-head"><h2>运行记录 <small>{{ page.total }} 条</small></h2><p class="q-muted">技术完成 ≠ 需求完成</p></div>
          <div class="q-table-wrap"><table class="q-run-table"><thead><tr><th>案例 / 运行</th><th>来源与执行</th><th>技术 / 业务结果</th><th>诊断分类</th><th>用量 / 计算费用</th><th>Trace / 耗时</th></tr></thead><tbody><tr v-for="r in page.items" :key="r.run_id"><td><RouterLink :to="runLocation(r.run_id)"><b>{{ r.case_id }} · {{ r.title }}</b><small>第 {{ r.repetition }} 次 · {{ label(r.target) }}</small></RouterLink><small>{{ when(r.started_at) }}</small></td><td>{{ label(r.data_origin) }}<small>{{ label(r.provenance) }}</small></td><td>{{ label(r.operation_status || r.execution_state) }}<small>{{ label(r.business_outcome) }}</small></td><td><span v-for="c in r.categories" :key="c" class="q-badge" :data-kind="c">{{ label(c) }}</span><span v-if="!r.categories.length">无 F/E 诊断</span><small>P {{ r.counts.P }} / F {{ r.counts.F }} / E {{ r.counts.E }} / U {{ r.counts.U }} / NA {{ r.counts.NA }}</small></td><td>{{ r.usage ? number(r.usage.total_tokens) + ' tokens' : r.actual_requests ? '用量未知' : '未调用真实模型' }}<small>{{ usd(r.cost_usd) }}</small></td><td>{{ r.trace_status === 'local_only' ? '本地 · 未上传云端' : 'Trace 缺失' }}<small>{{ seconds(r.wall_seconds) }}</small></td></tr></tbody></table></div>
          <p v-if="!page.items.length" class="q-empty">当前筛选下没有记录；可重置筛选查看全部案例。</p>
          <div class="q-pagination"><button :disabled="!value('cursor')" @click="setQuery({ cursor: '' }, false)">回到第一页</button><span>每页最多 20 条 · 总计 {{ page.total }}</span><button :disabled="!page.next_cursor" @click="setQuery({ cursor: page.next_cursor || '' }, false)">下一页</button></div>
        </div>
        <template v-else>
          <section class="q-panel"><div class="q-section-head"><h2>实验版本与成本</h2><span class="q-badge">本地冻结 · {{ page.summary.incomplete ? '部分完成' : '计划完成' }}</span></div><div class="q-two"><div><p>模型 <b>{{ page.experiment.model.name }}</b> · 温度 {{ page.experiment.model.temperature }} · {{ page.experiment.model.thinking }}</p><p>案例 {{ page.experiment.case_versions.join(' / ') }} · 评分器 {{ page.experiment.evaluator_versions.join(' / ') }}</p><details><summary>源码 / 数据 / 计划哈希</summary><pre>{{ page.experiment.source_sha256 }}
{{ page.experiment.dataset_sha256 }}
{{ page.experiment.plan_sha256 }}</pre></details></div><div><p>{{ page.experiment.pricing.basis }}</p><p>全实验输入 {{ number(page.experiment.pricing.input_tokens) }} / 输出 {{ number(page.experiment.pricing.output_tokens) }} / 输入缓存命中 {{ number(page.experiment.pricing.cache_read_tokens) }}</p><p>批准预算 {{ usd(page.experiment.pricing.budget_usd) }} · <a v-if="page.experiment.pricing.source_url" :href="page.experiment.pricing.source_url" target="_blank" rel="noopener noreferrer">官方费率</a></p></div></div><ul class="q-muted"><li v-for="l in page.experiment.limitations" :key="l">{{ l }}</li></ul></section>
          <section class="q-panel"><h2>四组诊断指标</h2><p class="q-muted">分母 = P + F + E + U；NA 单列。检查项和重复次数不是独立样本数。正式分数：未评估。</p><div class="q-table-wrap"><table><thead><tr><th>指标组</th><th>通过 P</th><th>失败 F</th><th>错误 E</th><th>未评 U</th><th>不适用 NA</th><th>适用分母</th></tr></thead><tbody><tr v-for="(m, key) in page.summary.metrics" :key="key"><td>{{ label(String(key)) }}</td><td>{{ m.P }}</td><td>{{ m.F }}</td><td>{{ m.E }}</td><td>{{ m.U }}</td><td>{{ m.NA }}</td><td>{{ m.applicable }}</td></tr><tr><td>运行成本</td><td colspan="6">真实请求 {{ page.summary.real_requests }}；用量覆盖 {{ page.summary.usage_known_runs }}/{{ page.summary.real_model_runs }}；费用覆盖 {{ page.summary.cost_known_runs }}/{{ page.summary.real_model_runs }}；{{ usd(page.summary.cost_usd) }}</td></tr></tbody></table></div></section>
          <section class="q-panel"><div class="q-section-head"><h2>基线 / 当前方案比较</h2><span class="q-badge">仅诊断差异</span></div><div class="q-compare-controls"><label>左实验<select v-model="leftId"><option v-for="e in experiments" :key="e.experiment_id" :value="e.experiment_id">{{ e.title }}</option></select></label><label>左方案<select v-model="leftVariant"><option v-for="v in leftExperiment?.variants" :key="v.variant" :value="v.variant">{{ label(v.variant) }}</option></select></label><label>右方案<select v-model="rightVariant"><option v-for="v in selectedExperiment?.variants" :key="v.variant" :value="v.variant">{{ label(v.variant) }}</option></select></label><button @click="loadComparison()" :disabled="loading">对比当前实验</button></div>
            <template v-if="comparison"><p class="q-context">{{ comparison.compatible ? '数据集 / 夹具 / 评分器版本一致，可查看诊断配对。' : '版本不一致，不具可比性，不计算改善或退步。' }}正式差值：未评估。</p><p>{{ comparison.pairing }}。可比较 {{ comparison.comparable_pairs }} 对，缺配对 {{ comparison.missing_pairs }} 对。</p><label class="q-inline">规则筛选<input v-model="compareRule" placeholder="例如 R-INTENT" aria-label="比较规则"></label><div class="q-table-wrap"><table><thead><tr><th>案例 / 重复</th><th>左侧</th><th>右侧</th><th>诊断变化</th></tr></thead><tbody><tr v-for="p in visiblePairs" :key="`${p.case_id}-${p.repetition}`"><td>{{ p.case_id }} / {{ p.repetition }}</td><td><RouterLink v-if="p.left" :to="runLocation(p.left, leftId)">{{ p.left }}</RouterLink><span v-else>缺配对</span></td><td><RouterLink v-if="p.right" :to="{ ...runLocation(p.right), query: { ...tabQuery, compare_id: p.left || undefined, compare_experiment: leftId } }">{{ p.right }}</RouterLink><span v-else>缺配对</span></td><td><span v-if="!p.comparable">{{ p.reason }}</span><template v-else><span v-for="c in p.changes.filter(c => (!compareRule || c.rule_id.includes(compareRule.toUpperCase())) && c.change !== 'unchanged')" :key="c.rule_id + c.layer" class="q-change">{{ c.rule_id }} / {{ label(c.layer) }}：{{ label(c.change) }}（{{ c.left }} → {{ c.right }}）</span><span v-if="p.changes.every(c => c.change === 'unchanged')">不变</span></template></td></tr></tbody></table></div></template>
          </section>
        </template>
      </template>
    </template>
  </main>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { qualityGet, label, number, usd, seconds, when, pretty, type QualityStatus, type Experiment, type RunPage, type RunDetail, type Comparison } from '@/services/quality'
import QualityMetrics from './QualityMetrics.vue'
import QualityDetail from './QualityDetail.vue'
import QualityChecks from './QualityChecks.vue'
import './quality.css'
const route = useRoute(), router = useRouter()
const status = ref<QualityStatus | null>(null), experiments = ref<Experiment[]>([]), page = ref<RunPage | null>(null), detail = ref<RunDetail | null>(null)
const paired = ref<RunDetail | null>(null)
const loading = ref(false), error = ref(''), stale = ref(false), cachedAt = ref(''), search = ref('')
const comparison = ref<Comparison | null>(null), leftId = ref(''), leftVariant = ref('baseline'), rightVariant = ref('current_live'), compareRule = ref('')
const categories = ['model_issue', 'reference_dispute', 'evidence_gap', 'fault_injection', 'unclassified']
const mode = computed(() => route.params.runId ? 'detail' : route.path.endsWith('experiments') ? 'experiments' : 'runs')
const value = (key: string, fallback = '') => typeof route.query[key] === 'string' ? route.query[key] as string : fallback
const selectedId = computed(() => value('experiment_id') || experiments.value[0]?.experiment_id || '')
const selectedExperiment = computed(() => experiments.value.find(e => e.experiment_id === selectedId.value))
const leftExperiment = computed(() => experiments.value.find(e => e.experiment_id === leftId.value))
const tabQuery = computed(() => ({ ...route.query, experiment_id: selectedId.value, cursor: undefined, compare_id: undefined, compare_experiment: undefined }))
const visiblePairs = computed(() => comparison.value?.pairs.filter(p => !compareRule.value || p.changes.some(c => c.rule_id.includes(compareRule.value.toUpperCase()))) || [])
let sequence = 0
async function get<T>(path: string) { const r = await qualityGet<T>(path); return r }
async function refresh() {
  const ticket = ++sequence; loading.value = true; error.value = ''; stale.value = false; page.value = null; detail.value = null; paired.value = null; comparison.value = null
  const accept = (r: { stale: boolean; cachedAt: string }) => { if (r.stale) { stale.value = true; cachedAt.value = r.cachedAt } }
  try {
    const state = await get<QualityStatus>('/status'); if (ticket !== sequence) return; status.value = state.data; accept(state)
    if (!state.data.enabled) { experiments.value = []; return }
    const list = await get<{ items: Experiment[] }>('/experiments'); if (ticket !== sequence) return; experiments.value = list.data.items; accept(list)
    if (!experiments.value.length) return
    search.value = value('q')
    if (mode.value === 'detail') {
      const r = await get<RunDetail>(`/runs/${encodeURIComponent(String(route.params.runId))}?experiment_id=${encodeURIComponent(selectedId.value)}`)
      if (ticket !== sequence) return; detail.value = r.data; accept(r)
      if (value('compare_id')) {
        const pair = await get<RunDetail>(`/runs/${encodeURIComponent(value('compare_id'))}?experiment_id=${encodeURIComponent(value('compare_experiment', selectedId.value))}`)
        if (ticket !== sequence) return; paired.value = pair.data; accept(pair)
      }
    } else {
      const q = queryParams(); const r = await get<RunPage>(`/runs?${q}`)
      if (ticket !== sequence) return; page.value = r.data; accept(r)
      if (mode.value === 'experiments') { leftId.value = value('left', selectedId.value); leftVariant.value = value('left_variant', 'baseline'); rightVariant.value = value('right_variant', 'current_live'); await loadComparison(false, ticket) }
    }
  } catch (e) { if (ticket === sequence) error.value = e instanceof Error ? e.message : '读取失败' }
  finally { if (ticket === sequence) loading.value = false }
}
function queryParams() { const q = new URLSearchParams(); for (const [k, v] of Object.entries(route.query)) if (typeof v === 'string' && !['left', 'left_variant', 'right_variant'].includes(k)) q.set(k, v); q.set('experiment_id', selectedId.value); if (!q.has('variant')) q.set('variant', 'current_live'); return q }
async function loadComparison(persist = true, ticket = sequence) {
  if (persist) { await setQuery({ left: leftId.value, left_variant: leftVariant.value, right_variant: rightVariant.value }); return }
  const q = queryParams(); q.delete('variant'); q.delete('cursor'); q.set('left', leftId.value); q.set('right', selectedId.value); q.set('left_variant', leftVariant.value); q.set('right_variant', rightVariant.value)
  const r = await get<Comparison>(`/experiments/compare?${q}`); if (ticket !== sequence) return; comparison.value = r.data; if (r.stale) { stale.value = true; cachedAt.value = r.cachedAt }
}
function setQuery(changes: Record<string, string>, clearCursor = true) { const q: LocationQueryRaw = { ...route.query, experiment_id: selectedId.value, ...changes }; if (clearCursor) delete q.cursor; if (changes.experiment_id) { delete q.left; delete q.left_variant; delete q.right_variant } return router.push({ path: route.path, query: q }) }
function change(key: string, event: Event) { void setQuery({ [key]: (event.target as HTMLSelectElement).value }) }
function applySearch() { void setQuery({ q: search.value }) }
function runLocation(id: string, experiment = selectedId.value) { return { path: `/quality/runs/${encodeURIComponent(id)}`, query: { ...tabQuery.value, experiment_id: experiment } } }
watch(() => route.fullPath, refresh, { immediate: true })
</script>
