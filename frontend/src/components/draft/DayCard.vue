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
        <section class="editor-section">
          <div class="section-header">
            <h4>开始时间</h4>
            <a-input
              v-model:value="dayStartTime"
              class="day-start-input"
              type="time"
              :disabled="!!busy"
              @change="onStartTimeChange"
            />
          </div>
        </section>

        <section class="editor-section">
          <div class="section-header">
            <h4>景点安排</h4>
          </div>
          <draggable v-model="orderedAttractions" item-key="name" handle=".drag-handle"
                     @end="onOrderChange" :disabled="!!busy">
            <template #item="{ element }">
              <div class="attr-row">
                <span class="drag-handle">⋮⋮</span>
                <span class="kind">📍</span>
                <span class="name">{{ element.name }}</span>
              </div>
            </template>
          </draggable>
        </section>

        <section class="editor-section">
          <div class="section-header">
            <h4>用餐安排</h4>
            <AddDiningPopover
              :pool="context.dining_pool"
              @add="onAddMeal"
            />
          </div>
          <div v-if="detail?.meals?.length" class="meal-list">
            <div v-for="m in detail.meals" :key="m.name + (m.category || m.type)" class="meal-row">
              <span class="kind">🍴</span>
              <span class="name">{{ m.name }}</span>
              <a-tag>{{ getMealLabel(m) }}</a-tag>
              <a-button size="small" danger @click="onRemoveMeal(m)" :disabled="!!busy">删除</a-button>
            </div>
          </div>
          <a-empty v-else class="meal-empty" description="还没有用餐安排" />
        </section>
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
const dayStartTime = ref('08:00')

watch(() => props.detail, (d) => {
  if (d?.attractions) orderedAttractions.value = [...d.attractions]
}, { immediate: true })

watch(
  () => [props.detail?.day_start_time, props.context?.day_start_time],
  ([detailTime, contextTime]) => {
    dayStartTime.value = detailTime || contextTime || '08:00'
  },
  { immediate: true },
)

let debounceTimer: any = null
function debouncedRecompute() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('recompute', {
      attractions_order: orderedAttractions.value.map(a => a.name),
      meals: (props.detail?.meals || []).map((m: any) => ({ ...m })),
    })
  }, 500)
}

function onOrderChange() { debouncedRecompute() }

function onStartTimeChange() {
  emit('recompute', {
    attractions_order: orderedAttractions.value.map(a => a.name),
    meals: (props.detail?.meals || []).map((m: any) => ({ ...m })),
    day_start_time: dayStartTime.value || props.context?.day_start_time || '08:00',
  })
}

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

const mealLabels: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  main: '正餐',
  snack: '小吃',
  dessert: '甜品',
  cafe: '咖啡',
  late_night: '夜宵',
}

function getMealLabel(meal: any) {
  const key = meal.category || meal.type
  return mealLabels[key] || '用餐'
}

const renderedDescription = computed(() => {
  return marked.parse(props.detail?.description || '') as string
})
</script>

<style scoped>
/* Bauhaus Card Wrapper */
:deep(.ant-card) {
  background: var(--white, #fff);
  border: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
  border-radius: 0;
  margin-bottom: var(--space-6, 24px);
}

:deep(.ant-card-head) {
  background: var(--primary-yellow, #F0C020);
  border-bottom: var(--border-main, 4px) solid var(--border, #121212);
  padding: var(--space-4, 16px) var(--space-6, 24px);
  border-radius: 0;
}

:deep(.ant-card-head-title) {
  font-size: var(--text-2xl, 20px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
}

:deep(.ant-card-body) {
  padding: var(--space-6, 24px);
}

.day-header {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
}

:deep(.ant-tag) {
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  color: var(--foreground, #121212);
  font-weight: var(--font-bold, 700);
}

.narrative {
  padding: 12px 0;
  line-height: 1.6;
}

.timeline {
  list-style: none;
  padding: 0;
}

.timeline li {
  padding: 4px 0;
}

.route-info {
  margin-top: 12px;
  background: var(--background, #F0F0F0);
  border: 2px solid var(--border, #121212);
  padding: var(--space-4, 16px);
}

.route-info h4 {
  margin-bottom: 8px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
}

.timeline-editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.editor-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.section-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
}

.day-start-input {
  width: 132px;
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  padding: 6px 12px;
  font-weight: var(--font-medium, 500);
}

.day-start-input:focus {
  outline: none;
  border-color: var(--primary-blue, #1040C0);
  box-shadow: 0 0 0 3px rgba(16, 64, 192, 0.1);
}

.meal-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.meal-empty {
  border: 2px dashed var(--border, #121212);
  border-radius: 0;
  padding: 8px 0;
  background: var(--background, #F0F0F0);
}

.attr-row, .meal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: var(--space-3, 12px);
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  position: relative;
}

.attr-row::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--primary-blue, #1040C0);
}

.meal-row::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--primary-red, #D02020);
}

.drag-handle {
  cursor: grab;
  color: var(--border, #121212);
  user-select: none;
  font-weight: var(--font-black, 900);
}

.kind {
  font-size: 16px;
}

.name {
  flex: 1;
  font-weight: var(--font-medium, 500);
}

.day-content {
  position: relative;
}

.day-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  z-index: 10;
  border: 4px solid var(--border, #121212);
}

.overlay-label {
  font-size: 14px;
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
  color: var(--foreground, #121212);
}

.day-loading {
  padding: 16px 0;
}

.loading-hint {
  text-align: center;
  color: var(--foreground, #121212);
  font-size: 13px;
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
  margin-top: 12px;
}
</style>
