<template>
  <article>
    <div class="q-section-head"><div><p class="q-eyebrow">{{ row.case_id }} · 第 {{ row.repetition }} 次 · {{ label(row.target) }}</p><h2 class="q-title">{{ row.title }}</h2></div><div class="q-actions"><button @click="copyId">{{ copied ? '已复制' : '复制运行 ID' }}</button><a class="q-button" :href="downloadUrl">导出脱敏记录</a></div></div>
    <p class="q-code">{{ row.run_id }} · {{ when(row.started_at) }}</p>
    <div class="q-tags"><span class="q-badge">{{ label(row.provenance) }}</span><span class="q-badge">{{ label(row.data_origin) }}</span><span class="q-badge">{{ label(row.operation_status || row.execution_state) }}</span><span class="q-badge">{{ label(row.business_outcome) }}</span><span v-for="c in row.categories" :key="c" class="q-badge" :data-kind="c">{{ label(c) }}</span></div>
    <div class="q-notice"><b>仅诊断 · 正式质量未评估</b><span>参考状态 {{ label(row.reference_status) }}。{{ row.case_version }} · {{ row.experiment.evaluator_versions.join(' / ') }}。{{ row.actual_requests }} 次真实请求，{{ number(row.usage?.total_tokens) }} tokens，{{ usd(row.cost_usd) }}（计算值，未核账单）。</span></div>
    <p v-if="row.provenance === 'injected_failure'" class="q-context">本例故障为预设注入；模型步骤不代表真实供应商请求，原始错误不计真实模型质量。</p>
    <div class="q-facts-grid">
      <section id="input-facts" class="q-panel"><h2>输入事实</h2><p v-if="hint" class="q-hint">{{ hint }}</p><p class="q-muted">冻结输入 · 外部事实回放</p><pre>{{ pretty(query || request) }}</pre>
        <template v-if="day"><h3>锁定与删除</h3><p>锁定：{{ pretty(day.locked_attraction_names) }}</p><p>删除：{{ pretty(day.removed_attraction_names) }}</p><h3>原时间轴</h3><ol class="q-timeline"><li v-for="(item, i) in timeline(day)" :key="i"><time>{{ item.start_time }}–{{ item.end_time }}</time><span>{{ item.ref_name }} <small>{{ item.duration }} 分钟</small></span></li></ol></template>
        <details><summary>全部脱敏输入 / 缓冲</summary><pre>{{ pretty(row.detail.inputs) }}</pre></details><details><summary>新旧来源记录</summary><pre>{{ pretty(row.detail.sources) }}</pre></details>
      </section>
      <section id="result-facts" class="q-panel"><h2>模型与最终结果</h2><h3>原始模型建议</h3><pre>{{ pretty(row.detail.raw_model) }}</pre>
        <h3>最终结果</h3><p v-if="row.detail.final_output?.message">{{ row.detail.final_output.message }}</p><ol v-if="finalTimeline.length" class="q-timeline"><li v-for="(item, i) in finalTimeline" :key="i"><time>{{ item.start_time }}–{{ item.end_time }}</time><span>{{ item.ref_name }} <small>{{ item.duration }} 分钟</small></span></li></ol>
        <details :open="!finalTimeline.length"><summary>完整脱敏结果 / 推荐</summary><pre>{{ pretty(row.detail.final_output) }}</pre></details><details><summary>保存前 / 并发最新 / 保存后</summary><h4>保存前</h4><pre>{{ pretty(row.detail.before) }}</pre><h4>并发最新</h4><pre>{{ pretty(row.detail.latest) }}</pre><h4>保存后</h4><pre>{{ pretty(row.detail.after) }}</pre></details>
        <p class="q-muted">HTTP {{ row.detail.http_status ?? '未记录' }} · {{ seconds(row.wall_seconds) }}</p>
      </section>
      <section class="q-panel"><QualityChecks :checks="row.checks" /></section>
    </div>
    <section v-if="row.detail.candidate_checks" class="q-panel"><div class="q-section-head"><h2>全部候选核对 · {{ row.detail.candidate_checks.length }}</h2><input v-model="search" placeholder="搜索候选 ID / 理由" aria-label="搜索候选"></div><div class="q-table-wrap"><table><thead><tr><th>候选</th><th>可行性</th><th>余量</th><th>排除 / 提示</th></tr></thead><tbody><tr v-for="c in candidates" :key="c.candidate_id"><td>{{ c.candidate_id }}</td><td>{{ c.eligible ? '保留' : '排除' }}{{ c.tight ? ' · 紧张' : '' }}</td><td>{{ pretty(c.margins) }}</td><td>{{ c.reasons.join('；') || '无排除理由' }}</td></tr></tbody></table></div></section>
    <QualityTrace :trace="row.detail.trace" />
  </article>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { label, number, usd, seconds, pretty, when, type RunDetail } from '@/services/quality'
import QualityChecks from './QualityChecks.vue'
import QualityTrace from './QualityTrace.vue'
const props = defineProps<{ row: RunDetail }>()
const copied = ref(false), search = ref('')
const hint = computed(() => props.row.detail.inputs.hint)
const query = computed(() => props.row.detail.inputs.query)
const request = computed(() => props.row.detail.inputs.request)
const day = computed(() => props.row.detail.inputs.day_detail as Record<string, unknown> | undefined)
type TimeItem = { start_time: string; end_time: string; ref_name: string; duration: number }
const timeline = (d: Record<string, unknown>) => (d.timeline_schedule || []) as TimeItem[]
const finalTimeline = computed(() => props.row.detail.final_output ? timeline(props.row.detail.final_output) : [])
const candidates = computed(() => props.row.detail.candidate_checks?.filter(c => `${c.candidate_id} ${c.reasons.join(' ')}`.includes(search.value)) || [])
const downloadUrl = computed(() => `/api/quality/runs/${encodeURIComponent(props.row.run_id)}?experiment_id=${encodeURIComponent(props.row.experiment.experiment_id)}&download=true`)
async function copyId() { try { await navigator.clipboard.writeText(props.row.run_id); copied.value = true } catch { copied.value = false } }
</script>
