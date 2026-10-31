<template>
  <div class="q-checks">
    <div class="q-section-head"><h2>逐项诊断证据</h2><label class="q-inline"><input v-model="failuresOnly" type="checkbox">仅失败 / 缺证据</label></div>
    <p class="q-muted">expected 是待审参考，不是已确认答案。点击证据字段可定位事实面板。</p>
    <details v-for="(c, i) in visible" :key="`${c.rule_id}-${c.layer}`" :open="c.status === 'FAIL' || c.status === 'ERROR'" class="q-check" :id="`check-${i}`">
      <summary><b>{{ c.rule_id }}</b><span>{{ label(c.layer) }}</span><span class="q-badge" :data-kind="c.status">{{ label(c.status) }}</span></summary>
      <p v-if="c.category" class="q-triage">{{ label(c.category) }}<span v-if="c.triage_note"> · {{ c.triage_note }}</span></p>
      <div class="q-two"><div><h4>实际证据</h4><pre>{{ pretty(c.actual) }}</pre></div><div><h4>待审预期</h4><pre>{{ pretty(c.expected) }}</pre></div></div>
      <p class="q-muted">{{ c.reason }}</p>
      <div class="q-evidence-links"><a v-for="path in c.evidence_paths" :key="path" :href="path.startsWith('trace') ? '#trace' : path.startsWith('raw_model') || path.startsWith('final_output') ? '#result-facts' : '#input-facts'">{{ path }}</a></div>
    </details>
    <p v-if="!visible.length" class="q-empty">此筛选下没有失败或缺证据项；不代表人工质量验收通过。</p>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { label, pretty, type Check } from '@/services/quality'
const props = defineProps<{ checks: Check[] }>()
const failuresOnly = ref(true)
const visible = computed(() => props.checks.filter(c => !failuresOnly.value || ['FAIL', 'ERROR'].includes(c.status)))
</script>
