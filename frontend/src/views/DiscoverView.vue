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

    <TripSetupSummary v-if="formData" :request="formData" compact />
    <section v-if="formData?.journey" class="joint-overview" aria-label="交通后的游玩时间">
      <div class="joint-windows"><div v-for="day in travelDays.filter((_:any,i:number)=>i===0||i===travelDays.length-1)" :key="day.date"><small>{{day.date}}</small><strong>{{day.window.unavailable||day.window.usable_minutes===0?'当天在途':timeLabel(Math.max(480,day.window.start_minutes??0))+'—'+timeLabel(Math.min(1320,day.window.end_minutes??1440))+' 可安排活动'}}</strong><span>{{day.window.provisional?'班次未齐，时间暂定':'已扣除抵离与接驳预留'}}</span></div></div>
      <details><summary>{{formData.journey.origin_city}} → {{formData.city}} → {{formData.journey.return_city}} · 查看班次、费用与接驳</summary><JourneySummary :journey="formData.journey" :city="formData.city" :days="travelDays.map((d:any)=>({date:d.date,travel_window:d.window}))" /></details>
    </section>
    <p v-else class="travel-notice">抵离交通未填写，首末日游玩时间暂定。</p>
    <details v-if="formData&&!multiRoute.query?.multi&&phase!=='planning'" class="joint-planning">
      <summary>交通与景点一起调整 <span>已选 {{selectedCount}} 个景点 · 可换班次，重新衔接每天</span></summary>
      <JourneyPlanner :model-value="formData.journey" :request="formData" :selected-visit-minutes="selectedVisitMinutes" :fixed-route="!!formData.journey?.origin_city" :disabled="aiSelectLoading||assignLoading||journeyUpdating" @update:model-value="updateJourney" @busy="journeySearching=$event" />
      <p v-if="journeyNotice" role="status">{{journeyNotice}}</p>
    </details>
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
          <div class="loading-text" role="status">正在查找 {{ formData?.city }} 的景点 <span>· 已等待 {{ elapsedSeconds }} 秒</span></div>
          <a-progress :percent="loadingProgress" :show-info="false" size="small" />
          <p class="search-status">{{ loadingMessage }}</p>
          <p v-if="elapsedSeconds >= 30" class="search-status">景点详情查询耗时较长。你可以先手动搜索并选择；停止搜索后，已有选择也会保留。</p>
          <button class="search-recovery" @click="stopDiscovery">停止搜索，保留当前选择</button>
        </div>
        <div v-else-if="discoveryNotice" class="loading-bar search-notice" role="status">
          <p>{{ discoveryNotice }}</p>
          <button class="search-recovery" :disabled="selectionLocked" @click="startDiscovery">重新搜索景点</button>
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
            <p>{{ attractions.length === 0 ? '还没有景点，可以重新搜索或手动添加' : '该分类下暂无景点' }}</p>
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
              <p>{{ attractions.length === 0 ? '还没有景点，可以重新搜索或手动添加' : '该分类下暂无景点' }}</p>
            </div>
          </div>
        </template>

        <!-- 加载更多 -->
        <div v-if="!loading && attractions.length > 0" class="load-more-bar">
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
            已选择 <strong>{{ selectedCount }}</strong> 个想去的地方
            <span v-if="selectedCount < 1" class="hint">（选择想去的景点）</span>
            <small v-else>{{assignmentEdited?'将沿用你确认的初步分组，继续核对路线与时间。':'接下来结合交通、营业时间与路线安排每天。'}}</small>
          </template>
        </div>
        <div class="selection-actions">
        <button class="optional-grouping" :disabled="selectionLocked||selectedCount<1" @click="startDayAssignment">{{assignLoading?'正在整理初步分组…':assignmentEdited?'查看已调整的分组':'初步分组（可选）'}}</button>
        <a-button
          type="primary"
          size="large"
          :disabled="selectionLocked || selectedCount < 1"
          @click="confirmAndPlan"
        >
          {{ aiSelectLoading ? '等待 AI 选择完成' : assignmentEdited?'按当前分组生成日程 →':'让 AI 安排日程 →' }}
        </a-button>
        </div>
        <p v-if="planningError" class="planning-error" role="alert">{{planningError}}</p>
      </div>
    </div>

    <!-- 可选预览：只有用户实际调整后，才将分组作为输入。 -->
    <div v-else-if="phase === 'assign'" class="assign-layout">
      <div class="assign-header">
        <div class="assign-header-main">
          <span class="assignment-kicker">{{assignmentEdited?'沿用当前分组':'可选 · 初步预览'}}</span>
          <h3>先看大致怎么玩，具体时间交给 AI</h3>
          <p>这是按位置和游览时长整理的初步分组。接下来核对交通、营业时间与实际路线，必要的调整会在草稿中展示。</p>
        </div>
        <button v-if="assignmentEdited" class="automatic-grouping" :disabled="selectionLocked" @click="resetToSmart">改为 AI 自动安排</button>
      </div>

      <div class="grouping-caption"><span>{{selectedCount}} 个想去的地方 · {{formData?.travel_days}} 天</span><span>游览时长不含路程与用餐 · 可拖动或选择日期</span></div>

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
              <span>第 {{ dayIdx + 1 }} 天</span><small>{{assignmentDate(dayIdx)}}</small>
            </span>
            <span
              class="day-duration-badge"
              :class="{ warning: dayDurations[dayIdx]?.warning }"
            >
              <template v-if="dayDurations[dayIdx]">
                游览约 {{ formatDuration(dayDurations[dayIdx].total_minutes) }}
              </template>
            </span>
          </div>
          <p v-if="travelDays[dayIdx]" class="grouping-window">
            {{ travelDays[dayIdx].window.unavailable ? '当天在途，不安排景点' : '可在 '+timeLabel(Math.max(480,travelDays[dayIdx].window.start_minutes ?? 0))+'—'+timeLabel(Math.min(1320,travelDays[dayIdx].window.end_minutes ?? 1440))+' 内安排活动' }}
            {{ travelDays[dayIdx].window.provisional ? '（暂定）' : '' }}
          </p>
          <div class="day-attractions">
            <div
              v-for="(attr, attrIdx) in day"
              :key="attr.name"
              class="draggable-mini-card"
              draggable="true"
              @dragstart="handleDragStart($event, dayIdx, attrIdx)"
            >
              <span class="mini-card-index" aria-hidden="true">{{String(attrIdx+1).padStart(2,'0')}}</span>
              <div class="mini-card-copy"><span class="mini-card-name">{{ attr.name }}</span><small>{{attr.category||'景点'}}<template v-if="attr.visit_minutes"> · 约 {{formatDuration(attr.visit_minutes)}}</template></small></div>
              <select
                class="day-move-select"
                :aria-label="`${attr.name}安排日期`"
                :value="dayIdx"
                @pointerdown.stop
                @dragstart.stop.prevent
                @change="moveAttraction(dayIdx, attrIdx, Number(($event.target as HTMLSelectElement).value))"
              >
                <option v-for="(_, targetDay) in dayAssignments" :key="targetDay" :value="targetDay" :disabled="travelDays[targetDay]?.window.unavailable">
                  第 {{ targetDay + 1 }} 天
                </option>
              </select>
            </div>
            <div v-if="day.length === 0" class="day-empty">{{travelDays[dayIdx]?.window.unavailable?'当天在途':"暂未分组到这天，可留给 AI 衔接。"}}</div>
          </div>
          <p v-if="dayDurations[dayIdx]?.warning" class="grouping-warning">{{dayDurations[dayIdx].warning}}，实际安排还需留出路程与用餐。</p>
        </div>
      </div>

      <div v-if="unassignedSelectionNames.length" class="grouping-pending"><strong>{{unassignedSelectionNames.length}} 个景点还需找合适的时段</strong><p>{{unassignedSelectionNames.join('、')}}。生成时会一起考虑，仍放不下的保留在待安排清单。</p></div>
      <p v-if="planningError" class="planning-error" role="alert">{{planningError}}</p>
      <div class="assign-actions">
        <button class="back-to-selection" :disabled="selectionLocked" @click="phase = 'discover'">← 返回景点选择</button>
        <a-button type="primary" size="large" :disabled="selectionLocked||selectedCount<1" @click="confirmAndPlan">
          {{assignmentEdited?'按当前分组生成日程 →':'让 AI 安排日程 →'}}
        </a-button>
      </div>
    </div>

    <!-- 阶段3: 规划中（由全局 BauhausLoader 覆盖展示） -->
    <div v-else-if="phase === 'planning'" class="planning-layout"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import JourneySummary from '@/components/JourneySummary.vue'
import JourneyPlanner from '@/components/JourneyPlanner.vue'
import TripSetupSummary from '@/components/TripSetupSummary.vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import SelectableAttractionCard from '@/components/SelectableAttractionCard.vue'
import DiscoveryMap from '@/components/DiscoveryMap.vue'
import { useTripLoader } from '@/composables/useTripLoader'
import { useDiscoverySearch } from '@/composables/useDiscoverySearch'
import { labelForNode, progressForNode } from '@/components/loader/constructionSteps'
import { sortAttractionsByRating } from '@/utils/discoverySort'
import { mergeDayAssignmentsWithSelected, hasUnsupportedEmptyDay, reserveAssignmentWindows } from '@/utils/dayAssignmentMerge'
import {
  applyAiSelectionRecommendations,
  isCurrentAiSelectionRequest,
} from '@/utils/aiSelectionState'
import {
  searchAttractionManual,
  createDraftFromSelectionsStream, previewDayAssignment,
  loadMoreAttractions, aiSelectAttractions, previewJourney,
} from '@/services/api'
import type { DraftStreamEvent } from '@/services/api'
import type { DiscoveredAttraction, TripFormData, DiscoveryStreamEvent, DayDurationInfo, Journey } from '@/types'

const router = useRouter()
const multiRoute = useRoute()
const tripLoader = useTripLoader()

const formData = ref<TripFormData | null>(null)
const journeyUpdating=ref(false),journeySearching=ref(false),journeyNotice=ref('')
let journeyGeneration=0
const travelDays=computed(()=>{try {const p=JSON.parse(sessionStorage.getItem('journeyPreview')||'null');return JSON.stringify(p?.request)===JSON.stringify(formData.value)?p.days:[]}catch{return []}})
function timeLabel(n:number){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
const attractions = reactive<DiscoveredAttraction[]>([])
const attractionPhotos = ref<Record<string, string>>({})
const weatherInfo = ref('')
const { loading, loadingMessage, loadingProgress, elapsedSeconds, discoveryNotice, search, stopDiscovery } = useDiscoverySearch(handleDiscoveryEvent)
const searchKeyword = ref('')
const searching = ref(false)
const searchResults = ref<DiscoveredAttraction[]>([])
const activeCategory = ref('全部')
const highlightedAttraction = ref('')
const phase = ref<'discover' | 'assign' | 'planning'>('discover')
const planningOriginPhase=ref<'discover'|'assign'>('discover')
const planningError=ref('')
const assignmentEdited=ref(false),assignmentSelectionKey=ref('')
const dayAssignments = ref<DiscoveredAttraction[][]>([])
const unassignedSelectionNames=computed(()=>{const assigned=new Set(dayAssignments.value.flatMap(day=>day.map(a=>a.name)));return attractions.filter(a=>a.selected&&!assigned.has(a.name)).map(a=>a.name)})
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

watch([attractions, dayAssignments, dayDurations, weatherInfo, phase, formData, assignmentEdited, assignmentSelectionKey], () => {
  if (!formData.value) return
  try {
    sessionStorage.setItem('discoveryRecovery', JSON.stringify({ form: formData.value,
      attractions, assignments: dayAssignments.value, durations: dayDurations.value,
      weather: weatherInfo.value, assignmentEdited:assignmentEdited.value, assignmentSelectionKey:assignmentSelectionKey.value,
      phase: phase.value === 'planning' ? planningOriginPhase.value : phase.value }))
  } catch { /* Existing in-memory choices remain usable if storage is full. */ }
}, { deep: true })

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
const selectionKey=computed(()=>JSON.stringify(attractions.filter(a=>a.selected).map(a=>[a.poi_id||'',a.name]).sort((a,b)=>a.join('|').localeCompare(b.join('|')))))
watch(selectionKey,key=>{
  if(dayAssignments.value.length&&key!==assignmentSelectionKey.value){
    dayAssignments.value=[];dayDurations.value=[];smartAssignmentCache.value=null;assignmentEdited.value=false;assignmentSelectionKey.value=''
  }
  planningError.value=''
})
const selectedVisitMinutes=computed(()=>attractions.filter(a=>a.selected).reduce((sum,a)=>sum+(a.visit_minutes||120),0))
const selectionLocked = computed(() => aiSelectLoading.value||journeyUpdating.value||journeySearching.value||assignLoading.value||phase.value==='planning')
const aiSelectDisabled = computed(
  () => selectionLocked.value || loading.value || attractions.length === 0
)

async function updateJourney(journey:Journey|null){
  if(!formData.value||aiSelectLoading.value||assignLoading.value||phase.value==='planning')return
  const current=++journeyGeneration
  const request:TripFormData=JSON.parse(JSON.stringify({...formData.value,journey}))
  journeyUpdating.value=true;journeyNotice.value='正在更新交通与每天的可用时间…'
  try{
    const preview=await previewJourney(request)
    if(current!==journeyGeneration)return
    sessionStorage.setItem('journeyPreview',JSON.stringify({request,days:preview.days}))
    sessionStorage.setItem('tripFormData',JSON.stringify(request))
    formData.value=request
    if(dayAssignments.value.length&&!assignmentEdited.value){
      const groups=dayAssignments.value.map(day=>[...day])
      const assigned=new Set(groups.flatMap(day=>day.map(a=>a.name)))
      if(!groups.length)groups.push([])
      groups[0].push(...attractions.filter(a=>a.selected&&!assigned.has(a.name)))
      dayAssignments.value=reserveAssignmentWindows(groups,preview.days.map((d:any)=>d.window))
      recalculateDayDurations();smartAssignmentCache.value=null
    }
    recalculateDayDurations()
    journeyNotice.value=assignmentEdited.value?'交通和可用时段已更新，当前分组已保留。你可以调整分组，或改为 AI 自动安排。':'已更新交通和可用时段，保留全部已选景点。每日路线与用餐会在生成日程时核对。'
  }catch{if(current===journeyGeneration)journeyNotice.value='这次交通修改未保存，请检查日期和班次；原景点与交通安排仍保留。'}
  finally{if(current===journeyGeneration)journeyUpdating.value=false}
}

function clearAssignmentPreview() {
  dayAssignments.value = []
  dayDurations.value = []
  smartAssignmentCache.value = null
  assignmentEdited.value=false
  assignmentSelectionKey.value=''
  planningError.value=''
}

function goBack() {
  router.push(multiRoute.query?.multi ? {path:'/multi-trip/'+String(multiRoute.query.multi),query:{city:String(multiRoute.query.stop||'')}} : '/')
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
      request: data,
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
  if (selectionLocked.value) return
  const selected = attractions.filter(a => a.selected)
  if (selected.length < 1) return
  planningError.value=''
  if(dayAssignments.value.length&&assignmentSelectionKey.value===selectionKey.value){phase.value='assign';return}

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
    while(dayAssignments.value.length<days) dayAssignments.value.push([])
    const openDays=travelDays.value.map((d:any,i:number)=>d.window.unavailable?-1:i).filter((i:number)=>i>=0)
    if(formData.value?.journey?.planning && travelDays.value.length===days){
      dayAssignments.value=reserveAssignmentWindows(dayAssignments.value,travelDays.value.map((d:any)=>d.window))
    }else if(openDays.length && travelDays.value.length===days){
      for(let i=0;i<days;i++){
        if(!travelDays.value[i].window.unavailable)continue
        const moved=dayAssignments.value[i].splice(0)
        for(const attraction of moved){const target=[...openDays].sort((a,b)=>dayAssignments.value[a].length-dayAssignments.value[b].length)[0];dayAssignments.value[target].push(attraction)}
      }
    }
    recalculateDayDurations()
    smartAssignmentCache.value = JSON.parse(JSON.stringify(dayAssignments.value))
    phase.value = 'assign'
  } catch (e: any) {
    message.warning('暂未取得分组建议，先按选择顺序展示；仍可交给 AI 继续规划。')
    const perDay = Math.ceil(selected.length / days)
    const assignments: DiscoveredAttraction[][] = []
    for (let d = 0; d < days; d++) {
      assignments.push(selected.slice(d * perDay, (d + 1) * perDay))
    }
    dayAssignments.value = assignments
    if(formData.value?.journey?.planning && travelDays.value.length===days)dayAssignments.value=reserveAssignmentWindows(assignments,travelDays.value.map((d:any)=>d.window))
    recalculateDayDurations()
    smartAssignmentCache.value = null
    phase.value = 'assign'
  } finally {
    assignmentEdited.value=false
    assignmentSelectionKey.value=selectionKey.value
    assignLoading.value = false
  }
}

function recalculateDayDurations() {
  dayDurations.value = dayAssignments.value.map((day, idx) => {
    const total = day.reduce((sum, a) => sum + (a.visit_minutes || 90), 0)
    return {
      day_index: idx,
      total_minutes: total,
      warning: total>availableMinutes(idx)?'游览已超出可用时段':total>480?'这天游览较多':null,
    }
  })
}

function resetToSmart() {
  if(smartAssignmentCache.value)dayAssignments.value = JSON.parse(JSON.stringify(smartAssignmentCache.value))
  if(travelDays.value.length===dayAssignments.value.length)dayAssignments.value=reserveAssignmentWindows(dayAssignments.value,travelDays.value.map((d:any)=>d.window))
  assignmentEdited.value=false;planningError.value=''
  recalculateDayDurations()
  message.success('已交给 AI 安排，全部已选景点会一起考虑')
}

function availableMinutes(index:number){const w=travelDays.value[index]?.window;return w?.unavailable?0:Math.max(0,Math.min(1320,w?.end_minutes??1440)-Math.max(480,w?.start_minutes??0))}
function assignmentDate(index:number){if(!formData.value?.start_date)return '';const date=new Date(formData.value.start_date+'T00:00:00');date.setDate(date.getDate()+index);return `${date.getMonth()+1}月${date.getDate()}日`}
function formatDuration(min: number): string {
  if (min < 60) return `${min} 分钟`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h} 小时 ${m} 分` : `${h} 小时`
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
  dragData = null
  moveAttraction(fromDay, fromIdx, toDay)
}

function moveAttraction(fromDay: number, fromIdx: number, toDay: number) {
  if (selectionLocked.value || fromDay === toDay || travelDays.value[toDay]?.window.unavailable || !dayAssignments.value[toDay] || !dayAssignments.value[fromDay]?.[fromIdx]) return
  const [item] = dayAssignments.value[fromDay].splice(fromIdx, 1)
  dayAssignments.value[toDay].push(item)
  assignmentEdited.value=true;planningError.value=''
  recalculateDayDurations()
}

async function confirmAndPlan() {
  if (!formData.value||selectionLocked.value||assignLoading.value) return
  const selected = attractions.filter(a => a.selected)
  if(!selected.length)return
  const useGrouping=assignmentEdited.value&&assignmentSelectionKey.value===selectionKey.value&&dayAssignments.value.length>0

  const hasEmpty = useGrouping&&hasUnsupportedEmptyDay(dayAssignments.value, !!multiRoute.query?.multi || !!formData.value.journey?.planning, travelDays.value.map((d:any)=>!!d.window.unavailable))
  if (hasEmpty) {
    planningError.value='当前分组有空白日期，请调整分组，或改为 AI 自动安排。'
    return
  }

  planningOriginPhase.value=phase.value==='assign'?'assign':'discover'
  planningError.value=''
  phase.value = 'planning'

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
      useGrouping?dayAssignments.value.map(day =>
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
      ):null,
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
          router.push({path:`/draft/${event.draft_id}`,query:multiRoute.query?.multi?{multi:multiRoute.query.multi,stop:multiRoute.query.stop,basis:multiRoute.query.basis,revision:multiRoute.query.revision}:{}})
        } else if (event.type === 'error') {
          window.clearTimeout(watchdog)
          tripLoader.dismiss()
          planningError.value=event.message||'本次规划未完成，已选景点已保留，可以重试。'
          message.error(planningError.value)
          phase.value = planningOriginPhase.value
        }
      }
    )
  } catch (e: any) {
    window.clearTimeout(watchdog)
    tripLoader.dismiss()
    planningError.value='本次规划未完成，已选景点已保留。'+(e.message||'请稍后重试。')
    message.error(planningError.value)
    phase.value = planningOriginPhase.value
  } finally {
    window.clearTimeout(watchdog)
  }
}

function handleDiscoveryEvent(event: DiscoveryStreamEvent) {
  if (event.type === 'attraction' && event.data) {
    // A retry may repeat already streamed POIs; preserve the user's selection.
    const candidate = event.data
    if (attractions.some(a => candidate.poi_id ? a.poi_id === candidate.poi_id : a.name === candidate.name && a.address === candidate.address)) return
    attractions.push({ ...candidate, selected: false, manuallyAdded: false })
    if (!candidate.image_url) loadPhotoForAttraction(candidate.name)
  } else if (event.type === 'weather' && event.data) {
    weatherInfo.value = event.data
  } else if (event.type === 'complete') {
    message.success(`发现 ${attractions.length} 个景点，请选择您感兴趣的景点`)
  }
}
async function startDiscovery() {
  if (formData.value) await search(formData.value)
}

onMounted(() => {
  const stored = sessionStorage.getItem('tripFormData')
  if (stored) {
    try {
      formData.value = JSON.parse(stored)
      try {
        const recovered = JSON.parse(sessionStorage.getItem('discoveryRecovery') || 'null')
        if (recovered && JSON.stringify(recovered.form) === JSON.stringify(formData.value)
            && recovered.attractions?.length) {
          attractions.push(...recovered.attractions)
          dayAssignments.value = recovered.assignments || []
          dayDurations.value = recovered.durations || []
          assignmentSelectionKey.value=recovered.assignmentSelectionKey||selectionKey.value
          // Old snapshots do not identify manual edits. Keep their groups until
          // the user explicitly chooses automatic planning or changes selection.
          assignmentEdited.value=recovered.assignmentEdited??(recovered.phase==='assign'&&dayAssignments.value.length>0)
          weatherInfo.value = recovered.weather || ''
          phase.value = recovered.phase === 'assign' ? 'assign' : 'discover'
          loading.value = false
          return
        }
      } catch { /* Fall back to a fresh discovery if the snapshot is invalid. */ }
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
.discover-page>.trip-setup-summary{width:calc(100% - 48px);max-width:1200px;margin:0 auto 12px}.joint-overview,.joint-planning{width:calc(100% - 48px)}
@media(max-width:650px){.discover-page>.trip-setup-summary,.joint-overview,.joint-planning{width:calc(100% - 28px)}}
.joint-planning{margin:18px auto;padding:16px 24px;max-width:1200px;border:1px solid var(--color-border);border-radius:14px;color:var(--color-text-primary);background:var(--color-bg-primary)}.joint-planning>summary{cursor:pointer;line-height:1.8}.joint-planning>summary span{font-size:12px;color:var(--color-text-secondary);margin-left:16px}
.joint-overview{margin:18px auto;padding:18px 24px;max-width:1200px;border:1px solid var(--color-border);border-radius:14px;color:var(--color-text-primary);background:var(--color-bg-primary)}.joint-windows{display:flex;flex-wrap:wrap;gap:20px;margin-bottom:14px}.joint-windows>div{display:flex;flex:1;flex-direction:column;gap:5px;min-width:220px}.joint-windows small,.joint-windows span{font-size:12px;color:var(--color-text-secondary)}.joint-windows strong{font-size:17px;font-weight:500}.joint-overview summary{cursor:pointer;font-size:13px;line-height:1.8}.joint-overview details[open]>summary{margin-bottom:16px}
.search-status { font-size: 13px; line-height: 1.7; margin: 8px 0; color: var(--text-secondary); }
.loading-text span { font-weight: 400; font-size: 13px; }
.search-recovery { padding: 8px 12px; border: 1px solid var(--border-color, #ddd); border-radius: 8px; background: var(--white, #fff); color: var(--text-primary); cursor: pointer; }
.search-recovery:focus-visible { outline: 2px solid #377861; outline-offset: 3px; }
.search-notice { line-height: 1.7; }

.travel-notice{padding:12px;background:#fff7d6;color:#222;line-height:1.5}
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

/* Optional grouping preview: an intention, not a verified daily schedule. */
.assign-layout { max-width:1200px; margin:24px auto 0; padding:0 0 36px; color:var(--color-text-primary); }
.assign-header { display:flex; justify-content:space-between; align-items:center; gap:24px; padding:26px 28px; margin-bottom:26px; border:1px solid var(--color-border); border-radius:18px; background:var(--color-bg-primary); }
.assign-header-main { max-width:760px; }
.assignment-kicker { color:var(--color-primary); font-size:11px; }
.assign-header h3 { font-size:23px; line-height:1.4; font-weight:500; letter-spacing:-.02em; margin:8px 0; color:var(--color-text-primary); }
.assign-header p { font-size:13px; line-height:1.9; color:var(--color-text-secondary); margin:0; }
.automatic-grouping,.optional-grouping,.back-to-selection { font:inherit; cursor:pointer; padding:9px 12px; border:0; background:none; color:var(--color-primary); font-size:12px; border-radius:8px; min-height:40px; }
.automatic-grouping { flex-shrink:0; border:1px solid var(--color-border-strong); background:var(--color-bg-primary); }
.automatic-grouping:disabled,.optional-grouping:disabled,.back-to-selection:disabled { opacity:.45; cursor:default; }
.grouping-caption { display:flex; justify-content:space-between; gap:14px; margin:0 2px 14px; font-size:12px; color:var(--color-text-secondary); }
.grouping-caption>span:last-child { font-size:11px; }
.day-columns { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr)); align-items:start; gap:16px; }
.day-column { padding:20px; min-width:0; border:1px solid var(--color-border); border-radius:16px; background:var(--color-bg-primary); }
.day-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px; }
.day-header-title { display:flex; align-items:center; gap:10px; font-size:14px; font-weight:600; }
.day-header-title small { font-size:11px; font-weight:400; color:var(--color-text-secondary); }
.day-duration-badge { font-size:11px; color:var(--color-text-secondary); padding:5px 8px; background:var(--color-bg-secondary); border-radius:6px; }
.day-duration-badge.warning { color:var(--color-warning); background:color-mix(in srgb,var(--color-warning) 7%,var(--color-bg-primary)); }
.grouping-window { margin:0 0 14px; font-size:11px; line-height:1.7; color:var(--color-text-secondary); }
.day-attractions { display:flex; flex-direction:column; gap:8px; }
.draggable-mini-card { display:flex; align-items:center; gap:12px; padding:14px 12px; border:1px solid var(--color-border); border-radius:10px; background:var(--color-bg-secondary); cursor:grab; transition:border-color .16s; }
.draggable-mini-card:hover { border-color:var(--color-border-strong); }
.draggable-mini-card:active { cursor:grabbing; }
.mini-card-index { font-size:10px; font-variant-numeric:tabular-nums; color:var(--color-text-secondary); opacity:.7; }
.mini-card-copy { flex:1; min-width:0; }
.mini-card-name { font-size:13px; font-weight:500; color:var(--color-text-primary); overflow-wrap:anywhere; }
.mini-card-copy small { display:block; font-size:10px; color:var(--color-text-secondary); margin-top:5px; }
.day-move-select { max-width:88px; min-height:34px; padding:6px; font:inherit; font-size:11px; border:1px solid var(--color-border-strong); border-radius:7px; color:var(--color-text-primary); background:var(--color-bg-primary); cursor:pointer; }
.day-empty { padding:28px 16px; text-align:center; color:var(--color-text-secondary); font-size:12px; line-height:1.8; border:1px dashed var(--color-border); border-radius:10px; }
.grouping-warning { font-size:11px; color:var(--color-warning); margin:14px 0 0; line-height:1.8; }
.grouping-pending { padding:18px 20px; margin-top:18px; border:1px solid var(--color-border); border-radius:12px; background:var(--color-bg-primary); font-size:13px; }
.grouping-pending p { font-size:12px; color:var(--color-text-secondary); margin:6px 0 0; line-height:1.8; }
.assign-actions { display:flex; justify-content:space-between; align-items:center; gap:16px; border-top:1px solid var(--color-border); margin-top:26px; padding-top:20px; }
.selection-actions { display:flex; align-items:center; gap:14px; }
.selection-info small { display:block; font-size:11px; font-weight:400; color:var(--color-text-secondary); margin-top:5px; }
.bottom-bar { flex-wrap:wrap; }
.planning-error { flex-basis:100%; padding:12px 16px; margin:8px 0 0; font-size:12px; line-height:1.8; color:var(--color-warning); border:1px solid color-mix(in srgb,var(--color-warning) 25%,var(--color-border)); border-radius:9px; background:var(--color-bg-primary); }
.assign-actions :deep(.ant-btn-primary) { min-height:44px; border-radius:9px; padding:10px 20px; height:auto; font-size:13px; box-shadow:none; }
.assign-layout :focus-visible,.selection-actions :focus-visible { outline:2px solid var(--color-primary); outline-offset:3px; }
@media(max-width:1248px) { .assign-layout { margin:24px 24px 0; } }
@media(max-width:650px) { .assign-layout { margin:18px 14px 0; }.assign-header { padding:20px; flex-direction:column; align-items:flex-start; gap:16px; }.assign-header h3 { font-size:21px; }.grouping-caption { flex-direction:column; gap:6px; }.day-column { padding:16px; }.assign-actions { flex-wrap:wrap; }.assign-actions :deep(.ant-btn-primary) { flex:1; }.selection-actions { display:grid; grid-template-columns:1fr; gap:6px; }.selection-actions .optional-grouping { order:2; }.mini-card-index { display:none; } }
@media(prefers-reduced-motion:reduce) { .draggable-mini-card { transition:none; } }

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
