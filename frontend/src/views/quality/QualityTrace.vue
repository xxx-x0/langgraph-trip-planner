<template>
  <section id="trace" class="q-panel">
    <div class="q-section-head"><h2>执行 Trace</h2><span class="q-badge">{{ trace.spans.length }} 个步骤 · 本地</span></div>
    <p class="q-muted">{{ trace.spans.length ? '已采集的原始执行步骤。嵌套耗时包含子步骤，不能相加作为总耗时。' : '本地 Trace 缺失，其他报告证据仍可查看。' }}</p>
    <p class="q-context">{{ trace.cloud_status === 'not_exported' ? '本批次未上传 LangSmith，无云端追踪链接。' : '云端导出状态未验证，无已验证链接。' }}</p>
    <p v-if="trace.operation_id" class="q-code">操作 {{ trace.operation_id }}</p>
    <div v-for="span in trace.spans" :key="span.id" class="q-span" :style="{ '--depth': depth(span) }">
      <details><summary><span class="q-span-name">{{ names[span.name] || span.name }}</span><span>{{ label(span.status) }}</span><b>{{ span.milliseconds?.toFixed(2) }} ms</b></summary>
        <div class="q-bar"><i :style="{ width: `${Math.max(.3, Math.min(100, span.milliseconds / total * 100))}%` }"></i></div>
        <p class="q-code">{{ span.name }} · {{ span.id }}</p><p class="q-muted">{{ span.start_time }} → {{ span.end_time }}</p><pre>{{ pretty(span.facts) }}</pre>
      </details>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { label, pretty, type Span, type RunDetail } from '@/services/quality'
const props = defineProps<{ trace: RunDetail['detail']['trace'] }>()
const total = computed(() => props.trace.spans[0]?.milliseconds || 1)
const names: Record<string, string> = { ticket_recommendation: '票务推荐', day_rearrangement: '每日重排', snapshot_read: '读取快照', eligibility: '可容纳性过滤', model_selection: '模型选择', model_suggestion: '模型建议', model_call: '真实/注入模型调用步骤', output_validation: '检查模型输出', constraint_repair: '约束修正', route_calculation: '路线核对', schedule_validation: '时间轴校验', saved_schedule_recovery: '恢复旧安排', fact_projection: '更新事实说明', cas_save: '快照校验与保存', snapshot_recheck: '重新检查快照', rule_fallback: '规则回退', response: '返回结果', external_attempt: '外部调用尝试', external_queue: '等待调用', external_result: '外部调用结果' }
function depth(span: Span) { let n = 0; let id = span.parent_id; const seen = new Set<string>(); while (id && !seen.has(id) && n < 5) { seen.add(id); n++; id = props.trace.spans.find(s => s.id === id)?.parent_id || null } return n }
</script>
