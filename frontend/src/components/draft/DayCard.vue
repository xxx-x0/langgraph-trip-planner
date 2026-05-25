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
  overflow: hidden;
}

:deep(.ant-card-head) {
  background: var(--primary-yellow, #F0C020);
  border-bottom: var(--border-main, 4px) solid var(--border, #121212);
  padding: var(--space-4, 16px) var(--space-12, 48px);
  border-radius: 0;
  position: relative;
}

/* 添加几何装饰到标题栏 */
:deep(.ant-card-head)::before {
  content: '';
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  background: var(--primary-red, #D02020);
  border: 2px solid var(--border, #121212);
  border-radius: 50%;
  z-index: 1;
}

:deep(.ant-card-head)::after {
  content: '';
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  background: var(--primary-blue, #1040C0);
  border: 2px solid var(--border, #121212);
  z-index: 1;
}

:deep(.ant-card-head-title) {
  font-size: var(--text-2xl, 20px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
  letter-spacing: 0.05em;
}

:deep(.ant-card-extra) {
  z-index: 2;
}

:deep(.ant-card-body) {
  padding: var(--space-6, 24px);
  background: var(--background, #F0F0F0);
}

.day-header {
  display: flex;
  gap: 12px;
  align-items: center;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

:deep(.ant-tag) {
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  color: var(--foreground, #121212);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  padding: 4px 10px;
  letter-spacing: 0.03em;
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

/* 叙述区 - 蓝色背景 */
.narrative {
  padding: var(--space-4, 16px);
  line-height: 1.7;
  background: var(--primary-blue, #1040C0);
  color: var(--white, #fff);
  border: 3px solid var(--border, #121212);
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
  margin-bottom: var(--space-6, 24px);
  position: relative;
  font-weight: var(--font-medium, 500);
}

.narrative::before {
  content: '✦';
  position: absolute;
  top: -16px;
  left: 16px;
  background: var(--primary-yellow, #F0C020);
  border: 3px solid var(--border, #121212);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: var(--font-black, 900);
  color: var(--foreground, #121212);
}

.timeline {
  list-style: none;
  padding: 0;
}

.timeline li {
  padding: 4px 0;
}

/* 路线信息 - 红色顶部条 */
.route-info {
  margin-top: var(--space-6, 24px);
  background: var(--white, #fff);
  border: 4px solid var(--border, #121212);
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
  padding: 0;
  overflow: hidden;
}

.route-info h4 {
  margin: 0;
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
  padding: var(--space-3, 12px) var(--space-4, 16px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 3px solid var(--border, #121212);
}

.route-info ul {
  list-style: none;
  padding: var(--space-4, 16px);
  margin: 0;
}

.route-info li {
  padding: var(--space-2, 8px) 0;
  font-weight: var(--font-medium, 500);
  border-bottom: 1px dashed var(--border, #121212);
}

.route-info li:last-child {
  border-bottom: none;
}

.timeline-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-6, 24px);
}

/* 编辑区段 - 包豪斯卡片样式 */
.editor-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
  background: var(--white, #fff);
  border: 3px solid var(--border, #121212);
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
  padding: 0;
  overflow: hidden;
}

/* 第一个section（开始时间）- 黄色顶部 */
.editor-section:nth-child(1) .section-header {
  background: var(--primary-yellow, #F0C020);
  color: var(--foreground, #121212);
}

/* 第二个section（景点安排）- 蓝色顶部 */
.editor-section:nth-child(2) .section-header {
  background: var(--primary-blue, #1040C0);
  color: var(--white, #fff);
}

/* 第三个section（用餐安排）- 红色顶部 */
.editor-section:nth-child(3) .section-header {
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: var(--space-3, 12px) var(--space-4, 16px);
  border-bottom: 3px solid var(--border, #121212);
}

.section-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* section 内部内容容器 */
.editor-section > :not(.section-header) {
  padding: var(--space-4, 16px);
}

.day-start-input {
  width: 132px;
  border: 3px solid var(--border, #121212);
  border-radius: 0;
  padding: 8px 12px;
  font-weight: var(--font-black, 900);
  font-size: 15px;
  background: var(--white, #fff);
  text-align: center;
}

.day-start-input:focus {
  outline: none;
  border-color: var(--primary-blue, #1040C0);
  box-shadow: 3px 3px 0px 0px var(--primary-blue, #1040C0);
}

.meal-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 8px);
}

.meal-empty {
  border: 3px dashed var(--border, #121212);
  border-radius: 0;
  padding: var(--space-4, 16px);
  background: var(--background, #F0F0F0);
}

/* 景点行 - 蓝色左边框 + 编号徽章 */
.attr-row {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  padding: var(--space-3, 12px) var(--space-4, 16px);
  border: 3px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  position: relative;
  transition: all 0.15s ease-out;
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
  margin-bottom: var(--space-2, 8px);
}

.attr-row:hover {
  transform: translate(-1px, -1px);
  box-shadow: 4px 4px 0px 0px var(--primary-blue, #1040C0);
}

.attr-row::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  background: var(--primary-blue, #1040C0);
}

/* 用餐行 - 红色左边框 */
.meal-row {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  padding: var(--space-3, 12px) var(--space-4, 16px);
  border: 3px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  position: relative;
  transition: all 0.15s ease-out;
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
}

.meal-row:hover {
  transform: translate(-1px, -1px);
  box-shadow: 4px 4px 0px 0px var(--primary-red, #D02020);
}

.meal-row::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  background: var(--primary-red, #D02020);
}

.drag-handle {
  cursor: grab;
  color: var(--border, #121212);
  user-select: none;
  font-weight: var(--font-black, 900);
  font-size: 18px;
  padding: 0 4px;
}

.drag-handle:active {
  cursor: grabbing;
}

.kind {
  font-size: 20px;
  background: var(--primary-yellow, #F0C020);
  border: 2px solid var(--border, #121212);
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.name {
  flex: 1;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0.02em;
  font-size: 14px;
}

.day-content {
  position: relative;
}

.day-overlay {
  position: absolute;
  inset: 0;
  background: rgba(240, 240, 240, 0.95);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  z-index: 10;
  border: 4px solid var(--border, #121212);
}

.overlay-label {
  font-size: 16px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--foreground, #121212);
  background: var(--primary-yellow, #F0C020);
  border: 3px solid var(--border, #121212);
  padding: var(--space-2, 8px) var(--space-4, 16px);
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
}

.day-loading {
  padding: var(--space-4, 16px);
  background: var(--white, #fff);
  border: 3px solid var(--border, #121212);
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
}

.loading-hint {
  text-align: center;
  color: var(--foreground, #121212);
  font-size: 14px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: var(--space-3, 12px);
  padding: var(--space-2, 8px);
  background: var(--primary-yellow, #F0C020);
  border: 2px solid var(--border, #121212);
}

/* 删除按钮包豪斯化 */
:deep(.ant-btn-dangerous) {
  background: var(--primary-red, #D02020) !important;
  color: var(--white, #fff) !important;
  border: 2px solid var(--border, #121212) !important;
  border-radius: 0 !important;
  font-weight: var(--font-black, 900) !important;
  text-transform: uppercase !important;
  box-shadow: 2px 2px 0px 0px var(--border, #121212) !important;
}

:deep(.ant-btn-dangerous:hover) {
  background: var(--foreground, #121212) !important;
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0px 0px var(--border, #121212) !important;
}

:deep(.ant-btn-link) {
  color: var(--foreground, #121212) !important;
  font-weight: var(--font-black, 900) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.03em !important;
}

:deep(.ant-btn-link:hover) {
  color: var(--primary-red, #D02020) !important;
  text-decoration: underline !important;
  text-decoration-thickness: 2px !important;
}
</style>
