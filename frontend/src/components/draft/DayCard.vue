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
      <a-button v-if="!isExpanded" type="link" @click="onExpand"
                :loading="busy === '装配中'">展开装配 →</a-button>
      <template v-else>
        <a-button type="link" @click="onAIRearrange"
                  :disabled="!!busy">AI 重新安排</a-button>
        <a-button type="link" @click="$emit('rewrite-narrative')"
                  :disabled="!!busy">重写叙述</a-button>
      </template>
    </template>

    <!-- 首次装配：骨架屏 -->
    <div v-if="isExpanded && !detail && busy === '装配中'" class="day-loading">
      <a-skeleton :active="true" :paragraph="{ rows: 4 }" />
      <div class="loading-hint">正在装配第 {{ context.day_index + 1 }} 天行程…</div>
    </div>

    <!-- 已装配内容（可叠加遮罩） -->
    <div v-else-if="isExpanded && detail" class="day-content">
      <div v-if="detail.description" class="narrative">
        <div v-html="renderedDescription"></div>
      </div>
      <div class="timeline-editor">
        <draggable v-model="orderedAttractions" item-key="name" handle=".drag-handle"
                   @end="onOrderChange" :disabled="!!busy">
          <template #item="{ element }">
            <div class="attr-row">
              <span class="drag-handle">⋮⋮</span>
              <span class="kind">📍</span>
              <span class="name">{{ element.name }}</span>
              <AddDiningPopover
                :pool="context.dining_pool"
                :insert-after="element.name"
                @add="onAddMeal"
              />
            </div>
          </template>
        </draggable>
        <div v-for="m in detail?.meals || []" :key="m.name + (m.category || m.type)" class="meal-row">
          <span class="kind">🍴</span>
          <span class="name">{{ m.name }}</span>
          <a-tag>{{ m.category || m.type }}</a-tag>
          <a-button size="small" danger @click="onRemoveMeal(m)" :disabled="!!busy">删除</a-button>
        </div>
      </div>
      <div class="route-info" v-if="detail.route_segments?.length">
        <h4>路线</h4>
        <ul>
          <li v-for="(seg, i) in detail.route_segments" :key="i">
            {{ seg.from_name }} → {{ seg.to_name }}: {{ seg.distance }} ({{ seg.duration }}, {{ seg.mode }})
          </li>
        </ul>
      </div>

      <!-- 非首次装配的遮罩 -->
      <div v-if="busy && busy !== '装配中'" class="day-overlay">
        <a-spin size="large" />
        <div class="overlay-label">{{ busy }}…</div>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { marked } from 'marked'
import AddDiningPopover from './AddDiningPopover.vue'

interface Props {
  context: any
  detail: any | null
  isDefaultExpanded: boolean
  busy?: string
}
const props = withDefaults(defineProps<Props>(), { busy: '' })
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
  const hint = window.prompt('AI 重排提示（可选，比如"我想吃辣的"）：', '')
  if (hint === null) return
  emit('ai-rearrange', hint || '')
}

const orderedAttractions = ref<any[]>([])

watch(() => props.detail, (d) => {
  if (d?.attractions) orderedAttractions.value = [...d.attractions]
}, { immediate: true })

let debounceTimer: any = null
function debouncedRecompute() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('recompute', {
      attractions_order: orderedAttractions.value.map(a => a.name),
      meals: (props.detail?.meals || []).map((m: any) => ({
        ...m,
        insert_after: m.insert_after || (orderedAttractions.value[
          Math.max(orderedAttractions.value.length / 2 - 1, 0) | 0
        ]?.name || ''),
      })),
    })
  }, 500)
}

function onOrderChange() { debouncedRecompute() }

function onAddMeal(meal: any) {
  const currentMeals = (props.detail?.meals || []).map((m: any) => ({ ...m }))
  currentMeals.push(meal)
  emit('recompute', {
    attractions_order: orderedAttractions.value.map(a => a.name),
    meals: currentMeals,
  })
}

function onRemoveMeal(meal: any) {
  const remaining = (props.detail?.meals || [])
    .filter((m: any) => !(m.name === meal.name && (m.category || m.type) === (meal.category || meal.type)))
  emit('recompute', {
    attractions_order: orderedAttractions.value.map(a => a.name),
    meals: remaining,
  })
}

const renderedDescription = computed(() => {
  return marked.parse(props.detail?.description || '') as string
})
</script>

<style scoped>
.day-header { display: flex; gap: 8px; align-items: center; }
.narrative { padding: 12px 0; line-height: 1.6; }
.timeline { list-style: none; padding: 0; }
.timeline li { padding: 4px 0; }
.route-info { margin-top: 12px; }
.route-info h4 { margin-bottom: 4px; }
.timeline-editor { display: flex; flex-direction: column; gap: 6px; }
.attr-row, .meal-row {
  display: flex; align-items: center; gap: 8px; padding: 6px;
  border: 1px solid #eee; border-radius: 4px;
}
.drag-handle { cursor: grab; color: #888; user-select: none; }
.kind { font-size: 16px; }
.name { flex: 1; }
.day-content {
  position: relative;
}
.day-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  z-index: 10;
  border-radius: 4px;
}
.overlay-label {
  font-size: 14px;
  color: #666;
}
.day-loading {
  padding: 16px 0;
}
.loading-hint {
  text-align: center;
  color: #999;
  font-size: 13px;
  margin-top: 12px;
}
</style>
