<template>
  <a-card>
    <template #title>
      <div class="day-header">
        <span>第 {{ context.day_index + 1 }} 天 · {{ context.date }}</span>
        <a-tag v-if="context.weather">
          {{ context.weather.day_weather }} {{ context.weather.day_temp }}°C
        </a-tag>
      </div>
    </template>
    <template #extra>
      <a-button v-if="!isExpanded" type="link" @click="onExpand">展开装配 →</a-button>
      <template v-else>
        <a-button type="link" @click="onAIRearrange">AI 重新安排</a-button>
        <a-button type="link" @click="$emit('rewrite-narrative')">重写叙述</a-button>
      </template>
    </template>

    <div v-if="isExpanded && detail">
      <div v-if="detail.description" class="narrative">
        <div v-html="renderedDescription"></div>
      </div>
      <ul class="timeline">
        <li v-for="(item, i) in detail.timeline_order" :key="i" :class="item.kind">
          <strong>{{ kindLabel(item.kind) }}</strong> {{ item.ref_name }}
        </li>
      </ul>
      <div class="route-info" v-if="detail.route_segments?.length">
        <h4>路线</h4>
        <ul>
          <li v-for="(seg, i) in detail.route_segments" :key="i">
            {{ seg.from_name }} → {{ seg.to_name }}: {{ seg.distance }} ({{ seg.duration }}, {{ seg.mode }})
          </li>
        </ul>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Props {
  context: any
  detail: any | null
  isDefaultExpanded: boolean
}
const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'assemble', body: any): void
  (e: 'recompute', body: any): void
  (e: 'ai-rearrange', hint: string): void
  (e: 'rewrite-narrative'): void
}>()

const isExpanded = ref(props.isDefaultExpanded)

watch(() => props.detail, (d) => {
  if (d && d.is_assembled) isExpanded.value = true
})

function onExpand() {
  isExpanded.value = true
  if (!props.detail) emit('assemble', {})
}

function onAIRearrange() {
  emit('ai-rearrange', '')
}

function kindLabel(kind: string) {
  return { hotel: '🏨', attraction: '📍', meal: '🍴' }[kind] || '·'
}

const renderedDescription = computed(() => {
  // 简易 markdown 渲染（T21 升级为 marked）
  return (props.detail?.description || '').replace(/\n/g, '<br>')
})
</script>

<style scoped>
.day-header { display: flex; gap: 8px; align-items: center; }
.narrative { padding: 12px 0; line-height: 1.6; }
.timeline { list-style: none; padding: 0; }
.timeline li { padding: 4px 0; }
.route-info { margin-top: 12px; }
.route-info h4 { margin-bottom: 4px; }
</style>
