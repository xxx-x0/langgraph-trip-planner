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
    <a-alert v-if="saveError" type="error" show-icon role="alert"
             :message="saveError" class="save-error" />
    <a-modal v-model:open="aiDialogOpen" title="AI 重排提示" ok-text="重新安排"
             cancel-text="取消" @ok="confirmAIRearrange">
      <a-textarea v-model:value="aiHint" aria-label="AI 重排提示（可选）"
                  placeholder="可选，比如：我想吃辣的" :rows="3" />
      <p>锁定景点保留当前位置，已删除景点不会重新加入。AI会保留已安排的正餐；需要减少餐次时，请先在草稿中手动删除。</p>
    </a-modal>
    <template #extra>
      <a-button v-if="!isExpanded" type="link" @click="onExpand"
                :loading="busy === '装配中'">展开装配 →</a-button>
      <template v-else>
        <a-button type="link" @click="onAIRearrange"
                  :disabled="!!busy">AI 重新安排</a-button>
        <a-button type="link" @click="$emit('rewrite-narrative')"
                  :disabled="!!busy">刷新行程说明</a-button>
      </template>
    </template>

    <!-- 首次装配：骨架屏 -->
    <div v-if="isExpanded && !detail && busy === '装配中'" class="day-loading">
      <a-skeleton :active="true" :paragraph="{ rows: 4 }" />
      <div class="loading-hint">正在装配第 {{ context.day_index + 1 }} 天行程…</div>
    </div>

    <!-- 已装配内容（可叠加遮罩） -->
    <div v-else-if="isExpanded && detail" class="day-content">
      <div class="narrative">
        <small>今天怎么逛 · 随你的修改更新</small>
        <div v-if="detail.description_source === 'itinerary_facts_v1'" class="description-text">{{ detail.description }}</div>
        <div v-else>旧版说明尚未核对当前安排，请刷新行程说明。</div>
      </div>
      <p v-if="detail.pending_confirmations?.length" class="next-step">下一步：{{ detail.pending_confirmations[0] }}</p>
      <details v-if="detail.pending_confirmations?.length" class="pending-confirmations">
        <summary>出发前还要确认 {{ detail.pending_confirmations.length }} 项</summary>
        <ul><li v-for="item in detail.pending_confirmations" :key="item">{{ item }}</li></ul>
      </details>
      <details v-if="detail.timeline_schedule?.length" class="schedule-details">
        <summary>查看时间安排和路上用时</summary>
        <DayTimeline :day="detail" />
      </details>
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
              <div class="attr-row" :class="{ 'attr-row-locked': isAttractionLocked(element.name) }">
                <span
                  :class="isAttractionLocked(element.name) ? 'drag-handle-static' : 'drag-handle'"
                >
                  ⋮⋮
                </span>
                <span class="kind">📍</span>
                <span class="name">{{ element.name }}</span>
                <div class="attr-actions">
                  <a-tooltip :title="isAttractionLocked(element.name) ? '取消排序锁定' : '锁定当前排序，不代表预约成功'">
                    <a-button
                      size="small"
                      class="icon-action"
                      :type="isAttractionLocked(element.name) ? 'primary' : 'default'"
                      :disabled="!!busy"
                      :aria-label="`${isAttractionLocked(element.name) ? '解锁' : '锁定'} ${element.name}`"
                      @click="onToggleLock(element.name)"
                    >
                      <template #icon>
                        <LockOutlined v-if="isAttractionLocked(element.name)" />
                        <UnlockOutlined v-else />
                      </template>
                    </a-button>
                  </a-tooltip>
                  <a-tooltip title="删除景点">
                    <a-button
                      size="small"
                      danger
                      class="icon-action"
                      :disabled="!!busy || isAttractionLocked(element.name)"
                      :aria-label="`删除 ${element.name}`"
                      @click="onRemoveAttraction(element.name)"
                    >
                      <template #icon><DeleteOutlined /></template>
                    </a-button>
                  </a-tooltip>
                </div>
              </div>
            </template>
          </draggable>
          <div v-if="removedAttractionNames.length" class="removed-list">
            <div v-for="name in removedAttractionNames" :key="name" class="removed-row">
              <span class="name">{{ name }}</span>
              <a-tooltip title="恢复景点">
                <a-button
                  size="small"
                  class="icon-action"
                  :disabled="!!busy"
                :aria-label="`恢复 ${name}`"
                  @click="onRestoreAttraction(name)"
                >
                  <template #icon><UndoOutlined /></template>
                </a-button>
              </a-tooltip>
            </div>
          </div>
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
          <p v-for="note in detail?.meal_adjustments || []" :key="note" role="status">ℹ️ {{ note }}</p>
          <p v-for="warning in detail?.meal_warnings || []" :key="warning" role="alert">⚠️ {{ warning }}</p>
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
import { ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { DeleteOutlined, LockOutlined, UndoOutlined, UnlockOutlined } from '@ant-design/icons-vue'
import DayTimeline from '../DayTimeline.vue'
import AddDiningPopover from './AddDiningPopover.vue'

interface Props {
  context: any
  detail: any | null
  isDefaultExpanded: boolean
  busy?: string
  saveError?: string
}
const props = withDefaults(defineProps<Props>(), { busy: '', saveError: '' })
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
  aiHint.value = ''
  aiDialogOpen.value = true
}

const aiDialogOpen = ref(false)
const aiHint = ref('')
function confirmAIRearrange() {
  if (props.busy) return
  aiDialogOpen.value = false
  emit('ai-rearrange', aiHint.value)
}

const orderedAttractions = ref<any[]>([])
const dayStartTime = ref('08:00')
const lockedAttractionNames = ref<string[]>([])
const removedAttractionNames = ref<string[]>([])

function restoreSavedState() {
  const d = props.detail
  orderedAttractions.value = [...(d?.attractions || [])]
  lockedAttractionNames.value = uniqueNames(d?.locked_attraction_names || [])
  removedAttractionNames.value = uniqueNames(d?.removed_attraction_names || [])
  dayStartTime.value = d?.day_start_time || props.context?.day_start_time || '08:00'
}

watch(() => props.detail, restoreSavedState, { immediate: true })
watch(() => props.busy, (busy, previous) => {
  if (previous && !busy) restoreSavedState()
})

watch(
  () => [props.detail?.day_start_time, props.context?.day_start_time],
  ([detailTime, contextTime]) => {
    dayStartTime.value = detailTime || contextTime || '08:00'
  },
  { immediate: true },
)

function uniqueNames(names: string[]) {
  return names.filter((name, index) => !!name && names.indexOf(name) === index)
}

function currentMeals() {
  const anchors = new Map<string, string>()
  let anchor = 'hotel_start'
  for (const item of props.detail?.timeline_order || []) {
    if (item.kind === 'attraction') anchor = item.ref_name
    else if (item.kind === 'hotel') anchor = item.phase === 'start' ? 'hotel_start' : 'hotel_end'
    else if (item.kind === 'meal') anchors.set(item.ref_name, anchor)
  }
  return (props.detail?.meals || []).map((m: any) => ({
    ...m, insert_after: anchors.get(m.name) || '',
  }))
}

function orderedNames() {
  return orderedAttractions.value.map(a => a.name)
}

function buildEditBody(extra: Record<string, any> = {}) {
  return {
    attractions_order: orderedNames(),
    locked_attraction_names: lockedAttractionNames.value,
    removed_attraction_names: removedAttractionNames.value,
    meals: currentMeals(),
    ...extra,
  }
}

function preserveLockedPositions(proposedNames: string[]) {
  const baseNames = (props.detail?.attractions || []).map((a: any) => a.name)
  const locked = new Set(lockedAttractionNames.value)
  if (!baseNames.length || !locked.size) return proposedNames

  const unlockedBase = baseNames.filter((name: string) => !locked.has(name))
  const proposedUnlocked = uniqueNames(proposedNames)
    .filter(name => unlockedBase.includes(name) && !locked.has(name))

  for (const name of unlockedBase) {
    if (!proposedUnlocked.includes(name)) proposedUnlocked.push(name)
  }

  const nextUnlocked = [...proposedUnlocked]
  return baseNames.map((name: string) => (
    locked.has(name) ? name : nextUnlocked.shift()
  )).filter(Boolean) as string[]
}

function reorderLocalAttractions(names: string[]) {
  const byName = new Map(orderedAttractions.value.map(a => [a.name, a]))
  orderedAttractions.value = names
    .map(name => byName.get(name))
    .filter(Boolean)
}

function onOrderChange() {
  const normalized = preserveLockedPositions(orderedNames())
  if (normalized.join('|') !== orderedNames().join('|')) {
    reorderLocalAttractions(normalized)
  }
  emit('recompute', buildEditBody())
}

function onStartTimeChange() {
  emit('recompute', buildEditBody({
    day_start_time: dayStartTime.value || props.context?.day_start_time || '08:00',
  }))
}

function onAddMeal(meal: any) {
  const meals = currentMeals()
  if (meals.some((m: any) => m.name === meal.name)) return
  meals.push(meal)
  emit('recompute', buildEditBody({ meals }))
}

function onRemoveMeal(meal: any) {
  const remaining = currentMeals()
    .filter((m: any) => !(m.name === meal.name && (m.category || m.type) === (meal.category || meal.type)))
  emit('recompute', buildEditBody({ meals: remaining }))
}

function isAttractionLocked(name: string) {
  return lockedAttractionNames.value.includes(name)
}

function onToggleLock(name: string) {
  lockedAttractionNames.value = isAttractionLocked(name)
    ? lockedAttractionNames.value.filter(item => item !== name)
    : [...lockedAttractionNames.value, name]
  emit('recompute', buildEditBody())
}

function onRemoveAttraction(name: string) {
  if (isAttractionLocked(name)) return
  removedAttractionNames.value = uniqueNames([...removedAttractionNames.value, name])
  lockedAttractionNames.value = lockedAttractionNames.value.filter(item => item !== name)
  orderedAttractions.value = orderedAttractions.value.filter(item => item.name !== name)
  emit('recompute', buildEditBody())
}

function onRestoreAttraction(name: string) {
  const restored = props.context?.attractions?.find((item: any) => item.name === name)
  if (!restored) return
  removedAttractionNames.value = removedAttractionNames.value.filter(item => item !== name)
  if (!orderedAttractions.value.some(item => item.name === name)) {
    orderedAttractions.value = [...orderedAttractions.value, restored]
  }
  emit('recompute', buildEditBody())
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


</script>

<style scoped>
.description-text { white-space: pre-line; }
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
.save-error {
  margin-bottom: 16px;
}
.attr-row-locked::before {
  background: var(--primary-yellow, #F0C020);
}
.attr-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 8px);
}
.icon-action {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}
.removed-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 8px);
  margin-top: var(--space-3, 12px);
}
.removed-row {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  padding: var(--space-2, 8px) var(--space-3, 12px);
  border: 2px dashed var(--border, #121212);
  background: var(--background, #F0F0F0);
  opacity: 0.78;
}
.removed-row .name {
  text-decoration: line-through;
}
.drag-handle-static {
  color: var(--border, #121212);
  opacity: 0.35;
  user-select: none;
  font-weight: var(--font-black, 900);
  font-size: 18px;
  padding: 0 4px;
}
</style>
