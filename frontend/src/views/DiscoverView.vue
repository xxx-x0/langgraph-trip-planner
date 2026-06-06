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
        <!-- AI 选景入口 -->
        <div class="ai-select-panel" :class="{ loading: aiSelectLoading }">
          <div class="ai-select-copy">
            <span class="ai-select-kicker">AI PICK</span>
            <h3>{{ aiSelectLoading ? 'AI 正在筛选景点' : 'AI 帮你先选一版' }}</h3>
            <p>
              {{
                aiSelectLoading
                  ? '正在根据天数、偏好和景点距离生成推荐，完成前暂时锁定选择。'
                  : '根据你的旅行偏好自动选出必去景点和备选景点，之后仍可手动微调。'
              }}
            </p>
          </div>
          <a-button
            class="ai-select-main-btn"
            type="primary"
            size="large"
            :loading="aiSelectLoading"
            :disabled="aiSelectDisabled"
            @click="handleAiSelect"
          >
            <template #icon><ThunderboltOutlined /></template>
            {{ aiSelectLoading ? '筛选中...' : 'AI 帮我选' }}
          </a-button>
        </div>

        <div v-if="aiSelectLoading" class="ai-select-loading-strip">
          <span>AI 正在筛选景点，请稍候</span>
          <div class="ai-select-loading-track">
            <div class="ai-select-loading-fill"></div>
          </div>
        </div>
        <div v-else-if="aiSelectSummary" class="ai-select-summary">
          {{ aiSelectSummary }}
        </div>

        <!-- 搜索栏 -->
        <div class="search-bar">
          <a-input-search
            v-model:value="searchKeyword"
            placeholder="手动搜索添加景点..."
            :loading="searching"
            :disabled="selectionLocked"
            @search="handleManualSearch"
          />
        </div>

        <!-- 搜索结果下拉 -->
        <div v-if="searchResults.length > 0" class="search-results-dropdown">
          <div
            v-for="result in searchResults"
            :key="result.name + (result.poi_id || '')"
            class="search-result-item"
            :class="{ disabled: selectionLocked }"
            @click="!selectionLocked && addSearchResult(result)"
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
            :disabled="selectionLocked"
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
        <template v-if="aiSelectionActive">
          <section v-if="mustAttractions.length > 0" class="reco-section">
            <h3 class="section-title">⭐ AI 推荐必去</h3>
            <div class="attractions-grid">
              <SelectableAttractionCard
                v-for="attr in mustAttractions"
                :key="attr.name + (attr.poi_id || '')"
                :attraction="attr"
                :photo-url="attractionPhotos[attr.name]"
                :disabled="selectionLocked"
                :ref="(el: any) => { if (el) cardRefs[attr.name] = el }"
                @toggle="toggleAttraction"
              />
            </div>
          </section>
          <section v-if="optionalAttractions.length > 0" class="reco-section">
            <h3 class="section-title">💡 备选推荐</h3>
            <div class="attractions-grid">
              <SelectableAttractionCard
                v-for="attr in optionalAttractions"
                :key="attr.name + (attr.poi_id || '')"
                :attraction="attr"
                :photo-url="attractionPhotos[attr.name]"
                :disabled="selectionLocked"
                :ref="(el: any) => { if (el) cardRefs[attr.name] = el }"
                @toggle="toggleAttraction"
              />
            </div>
          </section>
          <section v-if="otherAttractions.length > 0" class="reco-section">
            <h3 class="section-title">其他景点</h3>
            <div class="attractions-grid">
              <SelectableAttractionCard
                v-for="attr in otherAttractions"
                :key="attr.name + (attr.poi_id || '')"
                :attraction="attr"
                :photo-url="attractionPhotos[attr.name]"
                :disabled="selectionLocked"
                :ref="(el: any) => { if (el) cardRefs[attr.name] = el }"
                @toggle="toggleAttraction"
              />
            </div>
          </section>
          <div v-if="!loading && filteredAttractions.length === 0" class="empty-state">
            <p>{{ attractions.length === 0 ? '正在搜索景点...' : '该分类下暂无景点' }}</p>
          </div>
        </template>
        <template v-else>
          <div class="attractions-grid">
            <SelectableAttractionCard
              v-for="attr in filteredAttractions"
              :key="attr.name + (attr.poi_id || '')"
              :attraction="attr"
              :photo-url="attractionPhotos[attr.name]"
              :disabled="selectionLocked"
              :ref="(el: any) => { if (el) cardRefs[attr.name] = el }"
              @toggle="toggleAttraction"
            />
            <div v-if="!loading && filteredAttractions.length === 0" class="empty-state">
              <p>{{ attractions.length === 0 ? '正在搜索景点...' : '该分类下暂无景点' }}</p>
            </div>
          </div>
        </template>

        <!-- 加载更多 -->
        <div v-if="!loading" class="load-more-bar">
          <a-button
            type="dashed"
            block
            :loading="loadMoreLoading"
            :disabled="selectionLocked || loadMoreReachedLimit"
            @click="handleLoadMore"
          >
            {{ loadMoreReachedLimit ? '已达上限' : '加载更多 +20' }}
          </a-button>
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
          <template v-if="aiSelectLoading">
            AI 正在筛选景点，请稍候
          </template>
          <template v-else>
            已选择 <strong>{{ selectedCount }}</strong> 个景点
            <span v-if="selectedCount < 2" class="hint">（至少选择2个景点）</span>
          </template>
        </div>
        <a-button
          type="primary"
          size="large"
          :loading="assignLoading"
          :disabled="selectionLocked || selectedCount < 2"
          @click="startDayAssignment"
        >
          {{ aiSelectLoading ? '等待 AI 选择完成' : `开始规划 (${selectedCount}个景点) →` }}
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
            <span class="day-header-title">
              <span>第 {{ dayIdx + 1 }} 天</span>
              <a-tooltip placement="top">
                <template #title>已根据距离和时长自动均衡，可手动拖拽调整</template>
                <InfoCircleOutlined class="day-balance-info" />
              </a-tooltip>
            </span>
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

    <!-- 阶段3: 规划中（由全局 BauhausLoader 覆盖展示） -->
    <div v-else-if="phase === 'planning'" class="planning-layout"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { InfoCircleOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import SelectableAttractionCard from '@/components/SelectableAttractionCard.vue'
import DiscoveryMap from '@/components/DiscoveryMap.vue'
import { useTripLoader } from '@/composables/useTripLoader'
import { labelForNode, progressForNode } from '@/components/loader/constructionSteps'
import { sortAttractionsByRating } from '@/utils/discoverySort'
import { mergeDayAssignmentsWithSelected } from '@/utils/dayAssignmentMerge'
import {
  applyAiSelectionRecommendations,
  isCurrentAiSelectionRequest,
} from '@/utils/aiSelectionState'
import {
  discoverAttractionsStream, searchAttractionManual,
  createDraftFromSelectionsStream, previewDayAssignment,
  loadMoreAttractions, aiSelectAttractions,
} from '@/services/api'
import type { DraftStreamEvent } from '@/services/api'
import type { DiscoveredAttraction, TripFormData, DiscoveryStreamEvent, DayDurationInfo } from '@/types'

const router = useRouter()
const tripLoader = useTripLoader()

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

// Load more state
const loadMoreLoading = ref(false)
const loadMoreReachedLimit = ref(false)

// AI select state
const aiSelectLoading = ref(false)
const aiSelectRequestId = ref(0)
const aiSelectSummary = ref('')

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
  const items = activeCategory.value === '全部'
    ? attractions
    : attractions.filter(a => a.category === activeCategory.value)
  return sortAttractionsByRating(items)
})

const aiSelectionActive = computed(
  () => attractions.some((a: any) => a.recommendation)
)

const mustAttractions = computed(
  () => filteredAttractions.value.filter((a: any) => a.recommendation === 'must')
)
const optionalAttractions = computed(
  () => filteredAttractions.value.filter((a: any) => a.recommendation === 'optional')
)
const otherAttractions = computed(
  () => filteredAttractions.value.filter((a: any) => !a.recommendation)
)

const selectedCount = computed(() => attractions.filter(a => a.selected).length)
const selectionLocked = computed(() => aiSelectLoading.value)
const aiSelectDisabled = computed(
  () => aiSelectLoading.value || loading.value || attractions.length === 0
)

function clearAssignmentPreview() {
  dayAssignments.value = []
  dayDurations.value = []
  smartAssignmentCache.value = null
}

function goBack() {
  router.push('/')
}

function toggleAttraction(attr: DiscoveredAttraction) {
  if (selectionLocked.value) return
  const found = attractions.find(a => a.name === attr.name)
  if (found) {
    found.selected = !found.selected
    clearAssignmentPreview()
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
  if (selectionLocked.value) return
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
  if (selectionLocked.value) return
  attr.selected = true
  attr.manuallyAdded = true
  attractions.push(attr)
  searchResults.value = searchResults.value.filter(a => a.name !== attr.name)
  clearAssignmentPreview()
  message.success(`已添加: ${attr.name}`)
}

function toAiSelectAttractionPayload(a: DiscoveredAttraction) {
  return {
    poi_id: a.poi_id,
    name: a.name,
    description: a.description,
    address: a.address,
    category: a.category,
    rating: a.rating,
    ticket_price: a.ticket_price,
    image_url: a.image_url,
    location: a.location,
    open_hours: a.open_hours,
    visit_minutes: a.visit_minutes,
  }
}

function buildAiSelectPreferences(data: TripFormData) {
  return {
    interests: data.preferences,
    food_preference: data.food_preference,
    free_text_input: data.free_text_input,
    transportation: data.transportation,
    accommodation: data.accommodation,
    budget: data.budget,
    companions: data.companions,
  }
}

async function handleAiSelect() {
  if (aiSelectLoading.value) return
  const data = formData.value

  if (!data?.city || !data.travel_days) {
    message.error('请先选择目的地和天数')
    return
  }
  const city = data.city
  const days = data.travel_days
  if (attractions.length === 0) {
    message.info('景点加载后即可使用 AI 推荐')
    return
  }

  const requestId = aiSelectRequestId.value + 1
  aiSelectRequestId.value = requestId
  aiSelectLoading.value = true
  aiSelectSummary.value = ''
  searchResults.value = []

  try {
    message.loading({ content: 'AI 正在筛选景点…', key: 'ai-select', duration: 0 })

    const res = await aiSelectAttractions({
      destination: city,
      days,
      attractions: attractions.map(toAiSelectAttractionPayload),
      preferences: buildAiSelectPreferences(data),
    })

    if (!isCurrentAiSelectionRequest(requestId, aiSelectRequestId.value, aiSelectLoading.value)) {
      return
    }

    const mustSet = new Set(res.must_ids || [])
    const optionalSet = new Set(res.optional_ids || [])

    if (mustSet.size === 0 && optionalSet.size === 0) {
      message.destroy('ai-select')
      message.warning('未找到适合的推荐，请手动选择')
      return
    }

    const { mustCount, optionalCount } = applyAiSelectionRecommendations(
      attractions,
      mustSet,
      optionalSet,
      res.reasons || {},
      res.tags || {},
    )
    aiSelectSummary.value = res.summary || '已根据你的旅行偏好、景点类型和预计游玩时长生成推荐。'
    clearAssignmentPreview()
    message.destroy('ai-select')
    message.success(`已为你推荐 ${mustCount} 个必去 + ${optionalCount} 个备选`)
    document.querySelector('.bottom-bar')?.scrollIntoView({ behavior: 'smooth' })
  } catch (e: any) {
    if (!isCurrentAiSelectionRequest(requestId, aiSelectRequestId.value, aiSelectLoading.value)) {
      return
    }
    message.destroy('ai-select')
    message.error(e?.message || 'AI 推荐失败，请手动选择')
  } finally {
    if (isCurrentAiSelectionRequest(requestId, aiSelectRequestId.value, aiSelectLoading.value)) {
      message.destroy('ai-select')
      aiSelectLoading.value = false
    }
  }
}

async function handleLoadMore() {
  if (selectionLocked.value) return
  if (loadMoreLoading.value || loadMoreReachedLimit.value) return
  if (!formData.value?.city) {
    message.error('缺少城市信息，无法加载更多')
    return
  }
  loadMoreLoading.value = true
  try {
    const existingNames = new Set(attractions.map(a => a.name))
    const excludeNames = Array.from(existingNames)
    const res = await loadMoreAttractions({
      city: formData.value.city,
      exclude_names: excludeNames,
      batch_size: 20,
    })
    const returned = res.attractions || []
    const newOnes = returned.filter(a => !existingNames.has(a.name))
    if (newOnes.length > 0) {
      attractions.push(...newOnes)
      message.success(`已加载 ${newOnes.length} 个新景点`)
    } else {
      message.info('暂无更多景点')
    }
    if (attractions.length >= 100 || returned.length === 0) {
      loadMoreReachedLimit.value = true
    }
  } catch (e: any) {
    message.error(e?.message || '加载更多失败')
  } finally {
    loadMoreLoading.value = false
  }
}

async function startDayAssignment() {
  if (selectionLocked.value) {
    message.info('AI 正在筛选景点，请稍候')
    return
  }
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
    dayAssignments.value = mergeDayAssignmentsWithSelected(resp.day_assignments, selected)
    dayDurations.value = resp.day_durations
    smartAssignmentCache.value = JSON.parse(JSON.stringify(dayAssignments.value))
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

  const selected = attractions.filter(a => a.selected)

  // 启动全局 Bauhaus 加载海报（CONSTRUCTION）
  tripLoader.begin('construction', {
    city: formData.value.city,
    days: formData.value.travel_days,
    attractionCount: selected.length,
    // 注：weatherInfo 是后端原始天气载荷（Python str 化的 MCP content blocks，无法在前端可靠解析），
    // 仅作为 createDraftFromSelectionsStream 的入参透传给后端；海报 meta 用干净的日期区间。
    metaLine:
      formData.value.start_date && formData.value.end_date
        ? `${formData.value.start_date} – ${formData.value.end_date}`
        : undefined,
  })

  // 保险看门狗：仅提示、不强制撤场（后端可能仍在正常出结果）
  const watchdog = window.setTimeout(() => {
    if (tripLoader.state.phase !== 'idle' && tripLoader.state.phase !== 'flipping') {
      message.warning('生成耗时较长，请耐心等待…')
    }
  }, 90000)

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
        visit_minutes: a.visit_minutes,
        open_hours: a.open_hours,
        tel: a.tel,
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
          visit_minutes: a.visit_minutes,
          open_hours: a.open_hours,
          tel: a.tel,
        }))
      ),
      weatherInfo.value,
      (event: DraftStreamEvent) => {
        if (event.type === 'node_complete' && event.node) {
          tripLoader.setSteady()
          tripLoader.updateProgress(
            event.node,
            event.message || labelForNode(event.node),
            progressForNode(event.node),
          )
        } else if (event.type === 'complete' && event.draft_id) {
          // 立即切路由；loader 保持显示，由 DraftView 在第一天装配后 markReady 触发 Flip
          window.clearTimeout(watchdog)
          router.push(`/draft/${event.draft_id}`)
        } else if (event.type === 'error') {
          window.clearTimeout(watchdog)
          tripLoader.dismiss()
          message.error(event.message || '骨架生成失败')
          phase.value = 'assign'
        }
      }
    )
  } catch (e: any) {
    window.clearTimeout(watchdog)
    tripLoader.dismiss()
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
  background: var(--white, #fff);
}

/* Bauhaus Header - Yellow */
.discover-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--primary-yellow, #F0C020);
  border-bottom: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: none;
}

.header-content {
  max-width: var(--content-max-width, 1400px);
  margin: 0 auto;
  padding: var(--space-4, 16px) var(--space-6, 24px);
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  background: var(--white, #fff);
  border: 2px solid var(--border, #121212);
  cursor: pointer;
  font-size: 14px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
  padding: 8px 16px;
  border-radius: 0;
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
  transition: all 0.2s ease-out;
}

.back-btn:hover {
  transform: translate(1px, 1px);
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

.back-btn:active {
  transform: translate(3px, 3px);
  box-shadow: none;
}

.header-title {
  margin: 0;
  font-size: var(--text-2xl, 20px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
  flex: 1;
  letter-spacing: 0.02em;
}

.header-info {
  font-size: 14px;
  font-weight: var(--font-bold, 700);
  color: var(--foreground, #121212);
  background: var(--white, #fff);
  padding: 6px 16px;
  border: 2px solid var(--border, #121212);
  border-radius: 0;
}

/* === 发现布局 === */
.discover-layout {
  max-width: var(--content-max-width, 1400px);
  margin: 0 auto;
  padding: var(--space-4, 16px) var(--space-6, 24px);
  padding-bottom: 100px;
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 60px);
}

.left-panel {
  flex: 6;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 16px);
}

.right-panel {
  flex: 4;
  position: sticky;
  top: 76px;
  height: calc(100vh - 92px);
  border: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
  overflow: hidden;
}

.ai-select-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: var(--space-5, 20px);
  background: var(--primary-yellow, #F0C020);
  border: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
}

.ai-select-panel.loading {
  background: var(--primary-blue, #1040C0);
  color: var(--white, #fff);
}

.ai-select-copy {
  min-width: 0;
}

.ai-select-kicker {
  display: inline-block;
  margin-bottom: 6px;
  padding: 3px 8px;
  background: var(--white, #fff);
  border: 2px solid var(--border, #121212);
  color: var(--foreground, #121212);
  font-size: 11px;
  font-weight: var(--font-black, 900);
  letter-spacing: 0;
}

.ai-select-copy h3 {
  margin: 0;
  font-size: var(--text-2xl, 20px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  letter-spacing: 0;
  color: inherit;
}

.ai-select-copy p {
  margin: 6px 0 0;
  font-size: 13px;
  font-weight: var(--font-bold, 700);
  line-height: 1.5;
  color: inherit;
}

:deep(.ai-select-main-btn) {
  flex-shrink: 0;
  min-width: 160px;
  height: auto;
  padding: 12px 20px;
  border-radius: 0;
  border: 2px solid var(--border, #121212);
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
}

:deep(.ai-select-main-btn:hover) {
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
  transform: translate(1px, 1px);
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
}

:deep(.ai-select-main-btn:disabled) {
  background: var(--background, #F0F0F0);
  color: #777;
  border-color: #777;
  box-shadow: none;
  transform: none;
}

.ai-select-loading-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--white, #fff);
  border: 2px solid var(--border, #121212);
  font-size: 13px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
}

.ai-select-loading-track {
  flex: 1;
  height: 10px;
  overflow: hidden;
  border: 2px solid var(--border, #121212);
  background: var(--background, #F0F0F0);
}

.ai-select-loading-fill {
  width: 45%;
  height: 100%;
  background: var(--primary-blue, #1040C0);
  animation: ai-select-loading 1.2s ease-in-out infinite;
}

.ai-select-summary {
  padding: 12px 14px;
  background: var(--white, #fff);
  border: 2px solid var(--border, #121212);
  border-left: 8px solid var(--primary-blue, #1040C0);
  color: var(--foreground, #121212);
  font-size: 13px;
  font-weight: var(--font-bold, 700);
  line-height: 1.5;
}

@keyframes ai-select-loading {
  0% {
    transform: translateX(-110%);
  }
  100% {
    transform: translateX(230%);
  }
}

.search-bar {
  max-width: 560px;
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.search-bar :deep(.ant-input-search) {
  flex: 1;
}

/* Override Ant Design Input Search */
:deep(.ant-input-search) {
  border: 2px solid var(--border, #121212);
  border-radius: 0;
}

:deep(.ant-input-search .ant-input) {
  border: none;
  border-radius: 0;
  font-weight: var(--font-medium, 500);
}

:deep(.ant-input-search .ant-input-group-addon) {
  border: none;
  border-left: 2px solid var(--border, #121212);
  background: var(--primary-blue, #1040C0);
}

:deep(.ant-input-search .ant-btn) {
  border: none;
  background: transparent;
  color: var(--white, #fff);
  font-weight: var(--font-black, 900);
}

.search-results-dropdown {
  background: var(--white, #fff);
  border: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
  max-height: 240px;
  overflow-y: auto;
  margin-top: 8px;
}

.search-result-item {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  border-bottom: 2px solid var(--background, #F0F0F0);
  transition: background 0.15s;
}

.search-result-item:hover {
  background: var(--primary-yellow, #F0C020);
}

.search-result-item.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.result-name {
  font-weight: var(--font-bold, 700);
  flex-shrink: 0;
  color: var(--foreground, #121212);
}

.result-address {
  font-size: 12px;
  color: var(--foreground, #121212);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.result-add {
  color: var(--primary-blue, #1040C0);
  font-size: 13px;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  flex-shrink: 0;
}

.search-results-close {
  padding: 8px;
  text-align: center;
  color: var(--foreground, #121212);
  cursor: pointer;
  font-size: 12px;
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
  background: var(--background, #F0F0F0);
}

.search-results-close:hover {
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
}

.category-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-btn {
  padding: 8px 16px;
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  background: var(--white, #fff);
  color: var(--foreground, #121212);
  cursor: pointer;
  font-size: 13px;
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
  transition: all 0.2s ease-out;
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
}

.filter-btn:hover {
  transform: translate(1px, 1px);
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

.filter-btn:active {
  transform: translate(3px, 3px);
  box-shadow: none;
}

.filter-btn.active {
  background: var(--primary-blue, #1040C0);
  color: var(--white, #fff);
}

.filter-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: none;
}

.loading-bar {
  padding: var(--space-3, 12px) 0;
  background: var(--background, #F0F0F0);
  border: 2px solid var(--border, #121212);
  padding: var(--space-4, 16px);
}

.loading-text {
  font-size: 13px;
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
  color: var(--foreground, #121212);
  margin-bottom: 8px;
}

.attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-4, 16px);
}

.reco-section {
  margin-bottom: 24px;
}
.reco-section + .reco-section {
  margin-top: 24px;
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 16px 0 12px;
  color: var(--foreground, #1f1f1f);
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: var(--space-10, 40px);
  color: var(--foreground, #121212);
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
}

.load-more-bar {
  padding: var(--space-4, 16px);
  margin-top: var(--space-3, 12px);
}

/* === 底部操作栏 - Bauhaus Blue === */
.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--primary-blue, #1040C0);
  border-top: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: none;
  padding: var(--space-4, 16px) var(--space-6, 24px);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.selection-info {
  font-size: 15px;
  font-weight: var(--font-bold, 700);
  color: var(--white, #fff);
  text-transform: uppercase;
}

.selection-info strong {
  color: var(--primary-yellow, #F0C020);
  font-size: 24px;
  font-weight: var(--font-black, 900);
}

.hint {
  font-size: 12px;
  color: var(--white, #fff);
  margin-left: 8px;
  font-weight: var(--font-medium, 500);
}

/* Override Ant Design Button in bottom bar */
:deep(.bottom-bar .ant-btn-primary) {
  background: var(--primary-yellow, #F0C020);
  border: 2px solid var(--border, #121212);
  color: var(--foreground, #121212);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  border-radius: 0;
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
  height: auto;
  padding: 12px 32px;
  font-size: 14px;
}

:deep(.bottom-bar .ant-btn-primary:hover) {
  background: var(--primary-yellow, #F0C020);
  transform: translate(1px, 1px);
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
}

:deep(.bottom-bar .ant-btn-primary:active) {
  transform: translate(4px, 4px);
  box-shadow: none;
}

:deep(.bottom-bar .ant-btn-primary:disabled) {
  background: var(--background, #F0F0F0);
  color: #888;
  border-color: #888;
  box-shadow: none;
  transform: none;
}

/* === 日程分配 === */
.assign-layout {
  max-width: var(--content-max-width, 1400px);
  margin: 0 auto;
  padding: var(--space-6, 24px);
}

.assign-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-5, 20px);
  gap: 16px;
  background: var(--primary-yellow, #F0C020);
  border: var(--border-main, 4px) solid var(--border, #121212);
  padding: var(--space-6, 24px);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
}

.assign-header-main {
  flex: 1;
}

.assign-header h3 {
  margin: 0 0 8px;
  font-size: var(--text-2xl, 20px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
}

.assign-header p {
  margin: 0;
  font-size: 14px;
  font-weight: var(--font-medium, 500);
  color: var(--foreground, #121212);
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
  background: var(--white, #fff);
  border: var(--border-main, 4px) solid var(--border, #121212);
  box-shadow: var(--shadow-main, 8px 8px 0px 0px #121212);
  padding: var(--space-3, 12px);
  min-height: 200px;
  transition: transform 0.2s;
}

.day-column:hover {
  transform: translateY(-2px);
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  font-size: 15px;
  color: var(--foreground, #121212);
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border, #121212);
  margin-bottom: 8px;
}

.day-header-title {
  display: inline-flex;
  align-items: center;
}

.day-balance-info {
  margin-left: 6px;
  color: var(--color-text-secondary, #888);
  font-size: 14px;
  cursor: help;
}

.day-duration-badge {
  font-size: 11px;
  font-weight: var(--font-bold, 700);
  color: var(--foreground, #121212);
  background: var(--background, #F0F0F0);
  padding: 4px 8px;
  border: 2px solid var(--border, #121212);
  border-radius: 0;
}

.day-duration-badge.warning {
  background: var(--primary-red, #D02020);
  color: var(--white, #fff);
}

.day-attractions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.draggable-mini-card {
  padding: 10px 12px;
  background: var(--white, #fff);
  border: 2px solid var(--border, #121212);
  cursor: grab;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
  position: relative;
}

.draggable-mini-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--primary-blue, #1040C0);
}

.draggable-mini-card:hover {
  box-shadow: 4px 4px 0px 0px var(--border, #121212);
  transform: translate(-2px, -2px);
}

.draggable-mini-card:active {
  cursor: grabbing;
  box-shadow: 6px 6px 0px 0px var(--border, #121212);
  transform: translate(-3px, -3px);
}

.mini-card-name {
  font-size: 14px;
  font-weight: var(--font-bold, 700);
  color: var(--foreground, #121212);
  flex: 1;
}

.mini-card-tag {
  font-size: 11px;
  padding: 2px 8px;
  border: 2px solid var(--border, #121212);
  background: var(--primary-yellow, #F0C020);
  color: var(--foreground, #121212);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
}

.day-empty {
  padding: 20px;
  text-align: center;
  color: var(--foreground, #121212);
  font-size: 13px;
  font-weight: var(--font-bold, 700);
  text-transform: uppercase;
  border: 2px dashed var(--border, #121212);
  background: var(--background, #F0F0F0);
}

.assign-actions {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-6, 24px);
  padding-top: var(--space-4, 16px);
  border-top: var(--border-main, 4px) solid var(--border, #121212);
}

/* Override Ant Design Buttons in assign actions */
:deep(.assign-actions .ant-btn) {
  border: 2px solid var(--border, #121212);
  border-radius: 0;
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  box-shadow: 3px 3px 0px 0px var(--border, #121212);
  height: auto;
  padding: 10px 24px;
}

:deep(.assign-actions .ant-btn-primary) {
  background: var(--primary-blue, #1040C0);
  color: var(--white, #fff);
}

:deep(.assign-actions .ant-btn:hover) {
  transform: translate(1px, 1px);
  box-shadow: 2px 2px 0px 0px var(--border, #121212);
}

:deep(.assign-actions .ant-btn:active) {
  transform: translate(3px, 3px);
  box-shadow: none;
}

/* === 规划中 === */
.planning-layout {
  max-width: 600px;
  margin: 0 auto;
  padding: var(--space-16, 64px) var(--space-6, 24px);
}

.planning-container h3 {
  text-align: center;
  margin-bottom: var(--space-6, 24px);
  font-size: var(--text-2xl, 20px);
  font-weight: var(--font-black, 900);
  text-transform: uppercase;
  color: var(--foreground, #121212);
}

/* === 响应式 === */
@media (max-width: 768px) {
  .discover-layout {
    flex-direction: column;
    padding: var(--space-3, 12px);
  }

  .right-panel {
    position: relative;
    top: 0;
    height: 300px;
    order: -1;
  }

  .ai-select-panel {
    flex-direction: column;
    align-items: stretch;
  }

  :deep(.ai-select-main-btn) {
    width: 100%;
  }

  .ai-select-loading-strip {
    flex-direction: column;
    align-items: stretch;
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

  .bottom-bar {
    flex-direction: column;
    gap: var(--space-3, 12px);
    align-items: stretch;
  }

  .selection-info {
    text-align: center;
  }
}
</style>
