<template>
  <div class="discover-page">
    <!-- 顶部导航 -->
    <header class="discover-header">
      <div class="header-content">
        <button class="back-btn" @click="goBack">← 返回</button>
        <h2 class="header-title">{{ formData?.city }} · 景点发现</h2>
        <div class="header-info">{{ formData?.travel_days }}天行程</div>
      </div>
    </header>

    <!-- 阶段1: 景点发现与选择 -->
    <div v-if="phase === 'discover'" class="discover-layout">
      <!-- 左侧: 景点列表 -->
      <div class="left-panel">
        <!-- 搜索栏 -->
        <div class="search-bar">
          <a-input-search
            v-model:value="searchKeyword"
            placeholder="手动搜索添加景点..."
            :loading="searching"
            @search="handleManualSearch"
          />
        </div>

        <!-- 搜索结果下拉 -->
        <div v-if="searchResults.length > 0" class="search-results-dropdown">
          <div
            v-for="result in searchResults"
            :key="result.name + (result.poi_id || '')"
            class="search-result-item"
            @click="addSearchResult(result)"
          >
            <span class="result-name">{{ result.name }}</span>
            <span class="result-address">{{ result.address }}</span>
            <span class="result-add">+ 添加</span>
          </div>
          <div class="search-results-close" @click="searchResults = []">关闭</div>
        </div>

        <!-- 分类过滤 -->
        <div class="category-filters">
          <button
            v-for="cat in categories"
            :key="cat"
            class="filter-btn"
            :class="{ active: activeCategory === cat }"
            @click="activeCategory = cat"
          >
            {{ cat }}
          </button>
        </div>

        <!-- 加载进度 -->
        <div v-if="loading" class="loading-bar">
          <div class="loading-text">{{ loadingMessage }}</div>
          <a-progress :percent="loadingProgress" :show-info="false" size="small" />
        </div>

        <!-- 景点卡片网格 -->
        <div class="attractions-grid">
          <SelectableAttractionCard
            v-for="attr in filteredAttractions"
            :key="attr.name + (attr.poi_id || '')"
            :attraction="attr"
            :photo-url="attractionPhotos[attr.name]"
            :ref="(el: any) => { if (el) cardRefs[attr.name] = el }"
            @toggle="toggleAttraction"
          />
          <div v-if="!loading && filteredAttractions.length === 0" class="empty-state">
            <p>{{ attractions.length === 0 ? '正在搜索景点...' : '该分类下暂无景点' }}</p>
          </div>
        </div>
      </div>

      <!-- 右侧: 地图 -->
      <div class="right-panel">
        <DiscoveryMap
          ref="mapRef"
          :attractions="attractions"
          :highlighted-name="highlightedAttraction"
          @marker-click="handleMarkerClick"
        />
      </div>

      <!-- 底部操作栏 -->
      <div class="bottom-bar">
        <div class="selection-info">
          已选择 <strong>{{ selectedCount }}</strong> 个景点
          <span v-if="selectedCount < 2" class="hint">（至少选择2个景点）</span>
        </div>
        <a-button
          type="primary"
          size="large"
          :loading="assignLoading"
          :disabled="selectedCount < 2"
          @click="startDayAssignment"
        >
          开始规划 ({{ selectedCount }}个景点) →
        </a-button>
      </div>
    </div>

    <!-- 阶段2: 日程分配 -->
    <div v-else-if="phase === 'assign'" class="assign-layout">
      <div class="assign-header">
        <div class="assign-header-main">
          <h3>调整日程分配</h3>
          <p>系统已按地理距离与游玩时长智能分配，可拖拽景点微调</p>
        </div>
        <a-button @click="resetToSmart" :disabled="!smartAssignmentCache">
          🔄 重置为智能推荐
        </a-button>
      </div>

      <div class="day-columns">
        <div
          v-for="(day, dayIdx) in dayAssignments"
          :key="dayIdx"
          class="day-column"
          @dragover.prevent
          @drop="handleDrop($event, dayIdx)"
        >
          <div class="day-header">
            <span>第 {{ dayIdx + 1 }} 天</span>
            <span
              class="day-duration-badge"
              :class="{ warning: dayDurations[dayIdx]?.warning }"
            >
              <template v-if="dayDurations[dayIdx]">
                预计 {{ formatDuration(dayDurations[dayIdx].total_minutes) }}
                <span v-if="dayDurations[dayIdx].warning"> ⚠️</span>
              </template>
            </span>
          </div>
          <div class="day-attractions">
            <div
              v-for="(attr, attrIdx) in day"
              :key="attr.name"
              class="draggable-mini-card"
              draggable="true"
              @dragstart="handleDragStart($event, dayIdx, attrIdx)"
            >
              <span class="mini-card-name">{{ attr.name }}</span>
              <span v-if="attr.category" class="mini-card-tag">{{ attr.category }}</span>
            </div>
            <div v-if="day.length === 0" class="day-empty">拖拽景点到此处</div>
          </div>
        </div>
      </div>

      <div class="assign-actions">
        <a-button @click="phase = 'discover'">← 返回选择</a-button>
        <a-button type="primary" size="large" @click="confirmAndPlan">
          确认并生成行程 →
        </a-button>
      </div>
    </div>

    <!-- 阶段3: 规划中 -->
    <div v-else-if="phase === 'planning'" class="planning-layout">
      <div class="planning-container">
        <h3>正在生成行程计划...</h3>
        <PlanProgress
          :steps="planningSteps"
          :current-node="planningCurrentNode"
          :completed-nodes="planningCompletedNodes"
          :current-message="planningMessage"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import SelectableAttractionCard from '@/components/SelectableAttractionCard.vue'
import DiscoveryMap from '@/components/DiscoveryMap.vue'
import PlanProgress from '@/components/PlanProgress.vue'
import {
  discoverAttractionsStream, searchAttractionManual,
  createDraftFromSelectionsStream, previewDayAssignment,
} from '@/services/api'
import type { DraftStreamEvent } from '@/services/api'
import type { DiscoveredAttraction, TripFormData, DiscoveryStreamEvent, DayDurationInfo } from '@/types'

const router = useRouter()

const formData = ref<TripFormData | null>(null)
const attractions = reactive<DiscoveredAttraction[]>([])
const attractionPhotos = ref<Record<string, string>>({})
const weatherInfo = ref('')
const loading = ref(true)
const loadingMessage = ref('正在搜索景点...')
const loadingProgress = ref(0)
const searchKeyword = ref('')
const searching = ref(false)
const searchResults = ref<DiscoveredAttraction[]>([])
const activeCategory = ref('全部')
const highlightedAttraction = ref('')
const phase = ref<'discover' | 'assign' | 'planning'>('discover')
const dayAssignments = ref<DiscoveredAttraction[][]>([])
const dayDurations = ref<DayDurationInfo[]>([])
const smartAssignmentCache = ref<DiscoveredAttraction[][] | null>(null)
const assignLoading = ref(false)
const cardRefs: Record<string, any> = {}
const mapRef = ref<any>(null)

// Planning phase state
const planningCurrentNode = ref('')
const planningCompletedNodes = ref<Set<string>>(new Set())
const planningMessage = ref('')
const planningSteps = [
  { key: 'cluster_from_selections', label: '📊 聚类分析景点' },
  { key: 'search_food', label: '🍜 搜索美食' },
  { key: 'search_hotel', label: '🏨 搜索酒店' },
  { key: 'plan_route', label: '🗺️ 规划路线' },
  { key: 'macro_planner', label: '🏗️ 编排行程骨架' },
  { key: 'day_plan_subgraph', label: '📝 生成每日行程' },
  { key: 'reduce_assemble', label: '🔧 合并行程数据' },
  { key: 'global_synthesizer', label: '💡 生成全局建议' },
]

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function loadPhotoForAttraction(name: string) {
  if (attractionPhotos.value[name]) return
  const city = formData.value?.city || ''
  fetch(`${API_BASE_URL}/api/poi/photo?name=${encodeURIComponent(name)}&city=${encodeURIComponent(city)}`)
    .then(res => res.json())
    .then(data => {
      if (data.data?.photo_url) {
        attractionPhotos.value[name] = data.data.photo_url
      }
    })
    .catch(() => {})
}

const categories = computed(() => {
  const cats = new Set<string>()
  cats.add('全部')
  for (const a of attractions) {
    if (a.category) cats.add(a.category)
  }
  return Array.from(cats)
})

const filteredAttractions = computed(() => {
  if (activeCategory.value === '全部') return attractions
  return attractions.filter(a => a.category === activeCategory.value)
})

const selectedCount = computed(() => attractions.filter(a => a.selected).length)

function goBack() {
  router.push('/')
}

function toggleAttraction(attr: DiscoveredAttraction) {
  const found = attractions.find(a => a.name === attr.name)
  if (found) {
    found.selected = !found.selected
  }
}

function handleMarkerClick(attr: DiscoveredAttraction) {
  highlightedAttraction.value = attr.name
  const cardEl = cardRefs[attr.name]?.$el
  if (cardEl) {
    cardEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

async function handleManualSearch() {
  if (!searchKeyword.value.trim() || !formData.value) return
  searching.value = true
  try {
    const result = await searchAttractionManual(searchKeyword.value.trim(), formData.value.city)
    if (result.success && result.data.length > 0) {
      const existingNames = new Set(attractions.map(a => a.name))
      searchResults.value = result.data.filter(a => !existingNames.has(a.name))
      if (searchResults.value.length === 0) {
        message.info('搜索到的景点已在列表中')
      }
    } else {
      message.info('未搜索到相关景点')
      searchResults.value = []
    }
  } catch (e: any) {
    message.error('搜索失败: ' + (e.message || '未知错误'))
  } finally {
    searching.value = false
  }
}

function addSearchResult(attr: DiscoveredAttraction) {
  attr.selected = true
  attr.manuallyAdded = true
  attractions.push(attr)
  searchResults.value = searchResults.value.filter(a => a.name !== attr.name)
  message.success(`已添加: ${attr.name}`)
}

async function startDayAssignment() {
  const selected = attractions.filter(a => a.selected)
  if (selected.length < 2) return

  const days = formData.value?.travel_days || 1
  assignLoading.value = true
  try {
    const resp = await previewDayAssignment(selected, days)
    // 回写 visit_minutes 到 attractions（用 name 匹配）
    const nameToMinutes: Record<string, number> = {}
    for (const day of resp.day_assignments) {
      for (const attr of day) {
        if (attr.visit_minutes) nameToMinutes[attr.name] = attr.visit_minutes
      }
    }
    for (const a of attractions) {
      if (nameToMinutes[a.name]) a.visit_minutes = nameToMinutes[a.name]
    }
    dayAssignments.value = resp.day_assignments
    dayDurations.value = resp.day_durations
    smartAssignmentCache.value = JSON.parse(JSON.stringify(resp.day_assignments))
    phase.value = 'assign'
  } catch (e: any) {
    message.warning('智能分配失败，使用均分方案')
    const perDay = Math.ceil(selected.length / days)
    const assignments: DiscoveredAttraction[][] = []
    for (let d = 0; d < days; d++) {
      assignments.push(selected.slice(d * perDay, (d + 1) * perDay))
    }
    dayAssignments.value = assignments
    dayDurations.value = assignments.map((day, idx) => ({
      day_index: idx,
      total_minutes: day.reduce((sum, a) => sum + (a.visit_minutes || 90), 0),
      warning: null,
    }))
    smartAssignmentCache.value = null
    phase.value = 'assign'
  } finally {
    assignLoading.value = false
  }
}

function recalculateDayDurations() {
  dayDurations.value = dayAssignments.value.map((day, idx) => {
    const total = day.reduce((sum, a) => sum + (a.visit_minutes || 90), 0)
    return {
      day_index: idx,
      total_minutes: total,
      warning: total > 480 ? '当天偏紧' : null,
    }
  })
}

function resetToSmart() {
  if (!smartAssignmentCache.value) {
    message.info('无智能推荐结果可恢复')
    return
  }
  dayAssignments.value = JSON.parse(JSON.stringify(smartAssignmentCache.value))
  recalculateDayDurations()
  message.success('已恢复智能推荐')
}

function formatDuration(min: number): string {
  if (min < 60) return `${min}min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h${m}min` : `${h}h`
}

// Drag and drop
let dragData: { fromDay: number; fromIdx: number } | null = null

function handleDragStart(event: DragEvent, dayIdx: number, attrIdx: number) {
  dragData = { fromDay: dayIdx, fromIdx: attrIdx }
  event.dataTransfer?.setData('text/plain', '')
}

function handleDrop(_event: DragEvent, toDay: number) {
  if (!dragData) return
  const { fromDay, fromIdx } = dragData
  const [item] = dayAssignments.value[fromDay].splice(fromIdx, 1)
  dayAssignments.value[toDay].push(item)
  dragData = null
  recalculateDayDurations()
}

async function confirmAndPlan() {
  if (!formData.value) return

  const hasEmpty = dayAssignments.value.some(d => d.length === 0)
  if (hasEmpty) {
    message.warning('每天至少需要安排一个景点')
    return
  }

  phase.value = 'planning'
  planningCurrentNode.value = ''
  planningCompletedNodes.value = new Set()
  planningMessage.value = ''

  const selected = attractions.filter(a => a.selected)

  try {
    await createDraftFromSelectionsStream(
      formData.value,
      selected.map(a => ({
        name: a.name,
        description: a.description,
        address: a.address,
        category: a.category,
        rating: a.rating,
        ticket_price: a.ticket_price,
        image_url: a.image_url,
        location: a.location,
        poi_id: a.poi_id,
      })),
      dayAssignments.value.map(day =>
        day.map(a => ({
          name: a.name,
          description: a.description,
          address: a.address,
          category: a.category,
          rating: a.rating,
          ticket_price: a.ticket_price,
          image_url: a.image_url,
          location: a.location,
          poi_id: a.poi_id,
        }))
      ),
      weatherInfo.value,
      (event: DraftStreamEvent) => {
        if (event.type === 'node_complete' && event.node) {
          planningCompletedNodes.value = new Set([...planningCompletedNodes.value, event.node])
          planningCurrentNode.value = event.node
          planningMessage.value = event.message || ''
        } else if (event.type === 'complete' && event.draft_id) {
          message.success('骨架生成完成!')
          setTimeout(() => router.push(`/draft/${event.draft_id}`), 500)
        } else if (event.type === 'error') {
          message.error(event.message || '骨架生成失败')
          phase.value = 'assign'
        }
      }
    )
  } catch (e: any) {
    message.error('规划失败: ' + (e.message || '未知错误'))
    phase.value = 'assign'
  }
}

async function startDiscovery() {
  if (!formData.value) return

  loading.value = true
  loadingProgress.value = 5
  loadingMessage.value = '正在搜索景点...'

  try {
    await discoverAttractionsStream(
      formData.value,
      (event: DiscoveryStreamEvent) => {
        if (event.type === 'attraction' && event.data) {
          event.data.selected = false
          event.data.manuallyAdded = false
          attractions.push(event.data)
          if (!event.data.image_url) {
            loadPhotoForAttraction(event.data.name)
          }
        } else if (event.type === 'weather' && event.data) {
          weatherInfo.value = event.data
        } else if (event.type === 'progress') {
          loadingProgress.value = event.progress || 0
          loadingMessage.value = event.message || ''
        } else if (event.type === 'complete') {
          loading.value = false
          loadingProgress.value = 100
          const total = attractions.length
          message.success(`发现 ${total} 个景点，请选择您感兴趣的景点`)
        } else if (event.type === 'error') {
          loading.value = false
          message.error(event.message || '景点发现失败')
        }
      }
    )
  } catch (e: any) {
    loading.value = false
    message.error('景点发现失败: ' + (e.message || '未知错误'))
  }
}

onMounted(() => {
  const stored = sessionStorage.getItem('tripFormData')
  if (stored) {
    try {
      formData.value = JSON.parse(stored)
      startDiscovery()
    } catch {
      message.error('表单数据解析失败')
      router.push('/')
    }
  } else {
    message.error('未找到旅行表单数据')
    router.push('/')
  }
})
</script>

<style scoped>
.discover-page {
  min-height: 100vh;
  background: var(--color-bg-primary, #f5f5f5);
}

.discover-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--color-bg-elevated, #fff);
  border-bottom: 1px solid var(--color-border, #e8e8e8);
  box-shadow: var(--shadow-card, 0 2px 8px rgba(0,0,0,0.06));
}

.header-content {
  max-width: var(--content-max-width, 1400px);
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: var(--color-primary, #667eea);
  padding: 4px 8px;
  border-radius: var(--radius-sm, 6px);
}

.back-btn:hover {
  background: var(--color-bg-secondary, #f0f0f0);
}

.header-title {
  margin: 0;
  font-size: var(--font-size-xl, 20px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary);
  flex: 1;
}

.header-info {
  font-size: 14px;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary, #f0f0f0);
  padding: 4px 12px;
  border-radius: var(--radius-pill, 9999px);
}

/* === 发现布局 === */
.discover-layout {
  max-width: var(--content-max-width, 1400px);
  margin: 0 auto;
  padding: 16px 24px;
  padding-bottom: 80px;
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 60px);
}

.left-panel {
  flex: 6;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.right-panel {
  flex: 4;
  position: sticky;
  top: 76px;
  height: calc(100vh - 92px);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  box-shadow: var(--shadow-card, 0 2px 8px rgba(0,0,0,0.08));
}

.search-bar {
  max-width: 400px;
}

.search-results-dropdown {
  background: var(--color-bg-elevated, #fff);
  border: 1px solid var(--color-border, #e8e8e8);
  border-radius: var(--radius-md, 8px);
  box-shadow: var(--shadow-elevated, 0 4px 16px rgba(0,0,0,0.12));
  max-height: 240px;
  overflow-y: auto;
}

.search-result-item {
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--color-border-light, #f0f0f0);
}

.search-result-item:hover {
  background: var(--color-bg-secondary, #f5f5f5);
}

.result-name {
  font-weight: 500;
  flex-shrink: 0;
}

.result-address {
  font-size: 12px;
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.result-add {
  color: var(--color-primary, #667eea);
  font-size: 13px;
  font-weight: 500;
  flex-shrink: 0;
}

.search-results-close {
  padding: 8px;
  text-align: center;
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: 12px;
}

.category-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-btn {
  padding: 4px 14px;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-pill, 9999px);
  background: var(--color-bg-elevated, #fff);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: var(--color-primary, #667eea);
  color: var(--color-primary, #667eea);
}

.filter-btn.active {
  background: var(--color-primary, #667eea);
  border-color: var(--color-primary, #667eea);
  color: white;
}

.loading-bar {
  padding: 8px 0;
}

.loading-text {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 40px;
  color: var(--color-text-tertiary);
}

/* === 底部操作栏 === */
.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--color-bg-elevated, #fff);
  border-top: 1px solid var(--color-border, #e8e8e8);
  box-shadow: 0 -2px 8px rgba(0,0,0,0.06);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.selection-info {
  font-size: 15px;
  color: var(--color-text-primary);
}

.selection-info strong {
  color: var(--color-primary, #667eea);
  font-size: 20px;
}

.hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-left: 8px;
}

/* === 日程分配 === */
.assign-layout {
  max-width: var(--content-max-width, 1400px);
  margin: 0 auto;
  padding: 24px;
}

.assign-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}

.assign-header-main {
  flex: 1;
}

.assign-header h3 {
  margin: 0 0 4px;
  font-size: var(--font-size-xl, 20px);
  color: var(--color-text-primary);
}

.assign-header p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.day-columns {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding-bottom: 16px;
}

.day-column {
  flex: 1;
  min-width: 200px;
  background: var(--color-bg-elevated, #fff);
  border-radius: var(--radius-lg, 12px);
  border: 2px dashed var(--color-border, #d9d9d9);
  padding: 12px;
  min-height: 200px;
  transition: border-color 0.2s;
}

.day-column:hover {
  border-color: var(--color-primary, #667eea);
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text-primary);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light, #f0f0f0);
  margin-bottom: 8px;
}

.day-duration-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary, #f0f0f0);
  padding: 2px 8px;
  border-radius: var(--radius-pill, 9999px);
}

.day-duration-badge.warning {
  background: rgba(255, 77, 79, 0.1);
  color: #d4380d;
}

.day-attractions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.draggable-mini-card {
  padding: 10px 12px;
  background: var(--color-bg-secondary, #f5f5f5);
  border-radius: var(--radius-md, 8px);
  cursor: grab;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: box-shadow 0.2s;
}

.draggable-mini-card:active {
  cursor: grabbing;
  box-shadow: var(--shadow-elevated, 0 4px 12px rgba(0,0,0,0.15));
}

.mini-card-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
  flex: 1;
}

.mini-card-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--radius-pill, 9999px);
  background: var(--color-primary, #667eea);
  color: white;
}

.day-empty {
  padding: 20px;
  text-align: center;
  color: var(--color-text-disabled, #bbb);
  font-size: 13px;
}

.assign-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #e8e8e8);
}

/* === 规划中 === */
.planning-layout {
  max-width: 600px;
  margin: 0 auto;
  padding: 60px 24px;
}

.planning-container h3 {
  text-align: center;
  margin-bottom: 24px;
  font-size: var(--font-size-xl, 20px);
  color: var(--color-text-primary);
}

/* === 响应式 === */
@media (max-width: 768px) {
  .discover-layout {
    flex-direction: column;
    padding: 12px;
  }

  .right-panel {
    position: relative;
    top: 0;
    height: 300px;
    order: -1;
  }

  .attractions-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
  }

  .day-columns {
    flex-direction: column;
  }

  .day-column {
    min-width: auto;
  }
}
</style>
