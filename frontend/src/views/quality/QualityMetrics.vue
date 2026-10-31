<template>
  <div class="q-stats" aria-label="当前筛选统计">
    <div><span>已完成 / 计划槽位</span><strong>{{ s.completed }} <small>/ {{ s.planned }}</small></strong><p>{{ s.unique_cases }} 个独立案例 · {{ s.not_applicable }} 不适用 · {{ s.incomplete }} 未完成</p></div>
    <div><span>真实模型用量</span><strong>{{ number(s.tokens) }} <small>tokens</small></strong><p>{{ s.real_requests }} 次请求 · 用量覆盖 {{ s.usage_known_runs }}/{{ s.real_model_runs }} 个真实模型运行</p></div>
    <div><span>按实际用量计算 · 未核账单</span><strong class="q-cost">{{ usd(s.cost_usd) }}</strong><p>费用覆盖 {{ s.cost_known_runs }}/{{ s.real_model_runs }} · 峰时保守值 {{ usd(s.peak_cost_usd) }}</p></div>
    <div><span>有失败 / 缺证据的诊断</span><strong>{{ s.finding_runs }} <small>次运行</small></strong><p>{{ s.finding_cases }} 个案例 · {{ s.pending_cases }} 份参考待确认</p></div>
  </div>
  <div class="q-context">操作 p50 {{ seconds(s.wall_p50) }} · p95 {{ seconds(s.wall_p95) }}（{{ s.wall_count }} 次技术成功，{{ s.p95_small_sample ? '小样本' : '含重复案例' }}）；技术错误/超时 {{ s.technical_errors }}，规则回退 {{ s.fallback }}。预设故障与模型质量分开看。</div>
</template>
<script setup lang="ts">
import { number, usd, seconds, type Summary } from '@/services/quality'
defineProps<{ s: Summary }>()
</script>
