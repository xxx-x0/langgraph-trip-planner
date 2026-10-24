<template>
  <div class="result-container" :class="{ 'is-exporting': isExporting }">
    <div v-if="isStreaming && skeletonStage === 'error'" class="streaming-error">
      <a-result status="error" :title="streamError || '生成失败'">
        <template #extra>
          <a-button type="primary" @click="onRetry">重试</a-button>
          <a-button @click="backToDraft">返回草稿继续编辑</a-button>
        </template>
      </a-result>
    </div>

    <!-- SSE 流式生成期间的骨架屏：streaming 且 tripPlan 未填充时显示 -->
    <div
      v-if="isStreaming && !tripPlan && skeletonStage !== 'error'"
      class="result-skeleton"
    >
      <div class="hero-skeleton">
        <a-skeleton active :paragraph="{ rows: 2 }" />
        <p class="skeleton-hint">AI 正在为你定制行程…</p>
      </div>
      <div class="cards-skeleton">
        <a-skeleton active :paragraph="{ rows: 4 }" />
        <a-skeleton active :paragraph="{ rows: 4 }" />
        <a-skeleton active :paragraph="{ rows: 4 }" />
      </div>
    </div>

    <!-- 已保存旅行的阅读入口 -->
    <div v-if="tripPlan" class="result-hero" data-flip-id="loader-hero">
      <div class="hero-content">
        <button class="result-back" @click="router.push('/my-trips')">← 我的行程</button>
        <p class="result-eyebrow">YOUR TRAVEL NOTES · 旅行手册</p>
        <h1 class="hero-title">{{ tripPlan.title || tripPlan.city + '旅行计划' }}</h1>
        <p class="result-meta">{{ tripPlan.start_date }} — {{ tripPlan.end_date }}<span v-if="isSaved"> · 已保存的行程</span></p>
        <div class="hero-actions">
          <button class="hero-btn" @click="handleSaveTrip" :disabled="savingTrip || isSaved || isExporting">
            {{ isSaved ? '已保存' : '保存行程' }}
          </button>
          <button class="hero-btn" @click="exportAsImage" :disabled="isExporting">
            导出图片
          </button>
          <button class="hero-btn" @click="exportAsPDF" :disabled="isExporting">
            导出 PDF
          </button>
        </div>
      </div>
    </div>

    <!-- 旅行摘要 -->
    <div v-if="tripPlan" class="stats-section">
      <div class="stat-item">
        <div class="stat-value">{{ tripPlan.days?.length || 0 }}</div>
        <div class="stat-label">天数</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-value">{{ totalAttractions }}</div>
        <div class="stat-label">景点数</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-value">{{ tripPlan.budget ? '¥' + tripPlan.budget.total : '待核对' }}</div>
        <div class="stat-label">{{ tripPlan.budget?.is_complete === true ? '预估预算' : '已知费用小计' }}</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-value">{{ transportLabel }}</div>
        <div class="stat-label">交通方式</div>
      </div>
    </div>

    <div v-if="tripPlan" ref="tabAnchorRef" class="tab-anchor" aria-hidden="true"></div>
    <nav v-if="tripPlan" class="tab-bar" ref="tabBarRef" aria-label="行程内容">
      <div class="tab-bar-inner">
        <button
          v-for="tab in visibleTabs"
          :key="tab.key"
          class="tab-pill"
          :class="{ active: activeTab === tab.key }"
          :aria-pressed="activeTab === tab.key"
          :disabled="isExporting"
          :aria-controls="`result-panel-${tab.key}`"
          @click="activeTab = tab.key"
        >
          <span class="tab-icon" aria-hidden="true">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
        </button>
      </div>
    </nav>

    <div v-if="tripPlan" class="tab-content" ref="tabContentRef">
      <section v-if="visitedTabs.has('overview') || isExporting" v-show="activeTab === 'overview' || isExporting" id="result-panel-overview" class="result-panel" :class="{ 'is-active': activeTab === 'overview' }" aria-label="行程概览">
        <TabOverview :trip-plan="tripPlan" :expanded="isExporting" @open-day="openDay" />
      </section>
      <section v-if="visitedTabs.has('transport') || isExporting" v-show="activeTab === 'transport' || isExporting" id="result-panel-transport" class="result-panel" :class="{ 'is-active': activeTab === 'transport' }" aria-label="往返交通">
        <JourneySummary :journey="tripPlan.journey" :city="tripPlan.city" :days="tripPlan.days" :expanded="isExporting" />
      </section>
      <section v-if="(visitedTabs.has('budget') || isExporting) && tripPlan.budget" v-show="activeTab === 'budget' || isExporting" id="result-panel-budget" class="result-panel" :class="{ 'is-active': activeTab === 'budget' }" aria-label="费用明细">
        <TabBudget :budget="tripPlan.budget" :expanded="isExporting" />
      </section>
      <section v-show="activeTab === 'map' || isExporting" id="result-panel-map" class="result-panel" :class="{ 'is-active': activeTab === 'map' }" aria-label="行程地图">
        <TabMap ref="tabMapRef" :trip-plan="tripPlan" :attraction-photos="attractionPhotos" :visible="activeTab === 'map' || isExporting" />
      </section>
      <section v-if="visitedTabs.has('itinerary') || isExporting" v-show="activeTab === 'itinerary' || isExporting" id="result-panel-itinerary" class="result-panel" :class="{ 'is-active': activeTab === 'itinerary' }" aria-label="每日安排">
        <TabItinerary :trip-plan="tripPlan" :edit-mode="false" :expanded="isExporting" :attraction-photos="attractionPhotos" v-model:active-days="activeDays" />
      </section>
      <section v-if="(visitedTabs.has('weather') || isExporting) && tripPlan.weather_info?.length" v-show="activeTab === 'weather' || isExporting" id="result-panel-weather" class="result-panel" :class="{ 'is-active': activeTab === 'weather' }" aria-label="天气信息">
        <TabWeather :weather-info="tripPlan.weather_info" />
      </section>
    </div>

    <a-empty v-if="!tripPlan && !isStreaming" description="没有找到旅行计划数据">
      <template #image>
        <div style="font-size: 80px;">🗺️</div>
      </template>
      <template #description>
        <span style="color: var(--color-text-tertiary);">暂无旅行计划数据,请先创建行程</span>
      </template>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <a-back-top :visibility-height="300">
      <div class="back-top-button">↑</div>
    </a-back-top>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import JourneySummary from '@/components/JourneySummary.vue'
import type { TripPlan } from '@/types'
import { saveTripToHistory, getTripDetail, finalizeDraftStream } from '@/services/api'
import { useTripLoader } from '@/composables/useTripLoader'
import TabOverview from '@/components/result/TabOverview.vue'
import TabBudget from '@/components/result/TabBudget.vue'
import TabMap from '@/components/result/TabMap.vue'
import TabItinerary from '@/components/result/TabItinerary.vue'
import TabWeather from '@/components/result/TabWeather.vue'

const router = useRouter()
const route = useRoute()
const tripLoader = useTripLoader()

const isStreaming = computed(() => route.query.streaming === 'true')
const skeletonStage = ref<'init' | 'hero' | 'itinerary' | 'done' | 'error'>('init')
const streamError = ref<string | null>(null)
const streamInFlight = ref(false)

const tripPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeTab = ref('overview')
// Lazily mount each reading panel once, so switching keeps native disclosure state.
const visitedTabs = ref(new Set(['overview']))
const activeDays = ref<number[]>([0])
const isSaved = ref(false)
const savingTrip = ref(false)
const isExporting = ref(false)
const tabAnchorRef = ref<HTMLElement | null>(null)
const tabBarRef = ref<HTMLElement | null>(null)
const tabContentRef = ref<HTMLElement | null>(null)
const tabMapRef = ref<InstanceType<typeof TabMap> | null>(null)

const totalAttractions = computed(() => {
  if (!tripPlan.value?.days) return 0
  return tripPlan.value.days.reduce((sum, day) => sum + (day.attractions?.length || 0), 0)
})

const transportLabel = computed(() => {
  if (!tripPlan.value) return '-'
  const transport = tripPlan.value.transport_mode || tripPlan.value.days?.[0]?.transport_mode || tripPlan.value.days?.[0]?.transportation || ''
  const labels: Record<string, string> = {
    'driving': '自驾',
    'transit': '公交',
    'walking': '步行',
    'bicycling': '骑行'
  }
  return labels[transport] || transport || '-'
})

const visibleTabs = computed(() => {
  const tabs = [
    { key: 'overview', icon: '01', label: '行程概览' },
    { key: 'itinerary', icon: '02', label: '每日安排' },
    { key: 'transport', icon: '03', label: '往返交通' },
  ]
  if (tripPlan.value?.budget) tabs.push({ key: 'budget', icon: '04', label: '费用明细' })
  tabs.push({ key: 'map', icon: '05', label: '行程地图' })
  if (tripPlan.value?.weather_info?.length) tabs.push({ key: 'weather', icon: '06', label: '天气信息' })
  return tabs
})

function openDay(index: number) {
  activeDays.value = [index]
  activeTab.value = 'itinerary'
}
watch(activeTab, async (tab) => {
  visitedTabs.value.add(tab)
  await nextTick()
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const anchor = tabAnchorRef.value
  // Measure the normal-flow anchor: a sticky bar itself always remains at the top.
  if (anchor) {
    window.scrollTo({ top: Math.max(0, window.scrollY + anchor.getBoundingClientRect().top - 64), behavior: reduce ? 'auto' : 'smooth' })
  }
  tabBarRef.value?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus({ preventScroll: true })
})

onMounted(async () => {
  if (isStreaming.value) {
    await startStreaming()
    return
  }
  const tripId = route.params.id
  if (tripId) {
    await loadTripFromHistory(Number(tripId))
  } else {
    const data = sessionStorage.getItem('tripPlan')
    if (data) {
      try {
        tripPlan.value = JSON.parse(data)
      } catch (e) {
        message.error('行程数据解析失败')
      }
    }
  }
  if (tripPlan.value) {
    await loadAttractionPhotos()
  }
})

async function startStreaming() {
  if (streamInFlight.value) return
  const draftId = route.query.draft_id as string
  if (!draftId) {
    streamError.value = '缺少 draft_id'
    skeletonStage.value = 'error'
    return
  }
  streamError.value = null
  streamInFlight.value = true
  skeletonStage.value = 'init'

  try {
    let progressCount = 0
    await finalizeDraftStream(draftId, async (event: any) => {
      if (event.type === 'progress') {
        progressCount++
        if (progressCount === 1) skeletonStage.value = 'hero'
        else if (progressCount === 2) skeletonStage.value = 'itinerary'
        // 驱动 Poster B 底部状态条真实 SSE 文案（progress=0：不确定态，不显示百分比）
        tripLoader.updateProgress(event.step, event.message, 0)
      } else if (event.type === 'complete') {
        tripPlan.value = event.trip_plan
        skeletonStage.value = 'done'
        // 把 URL 改成 /trip/:id 以便后续分享和刷新；但 tripPlan 已填充，无需重新加载
        if (event.trip_id) {
          isSaved.value = true
          await router.replace({ path: `/trip/${event.trip_id}` })
        }
        if (tripPlan.value) {
          await loadAttractionPhotos()
        }
        // tripPlan 已填充且路由已切换：.result-hero 此刻才在 DOM 中，
        // 等下一帧 DOM 落定后再 markReady()，Flip 才找得到 [data-flip-id="loader-hero"] 落点
        await nextTick()
        tripLoader.markReady()
      } else if (event.type === 'error') {
        streamError.value = event.message || '生成失败'
        skeletonStage.value = 'error'
        tripLoader.dismiss() // 直接撤场，露出 error skeleton + 重试按钮
      }
    })
  } catch (e: any) {
    streamError.value = e?.message || '连接失败'
    skeletonStage.value = 'error'
    tripLoader.dismiss() // 含 finalizeDraftStream 180s fetch 超时：撤场露出 error skeleton
  } finally {
    streamInFlight.value = false
  }
}

function backToDraft() {
  router.push(`/draft/${route.query.draft_id}`)
}

function onRetry() {
  startStreaming()
}

const goBack = () => { router.push('/') }

const loadTripFromHistory = async (tripId: number) => {
  try {
    const res = await getTripDetail(tripId)
    if (res.data?.plan) {
      tripPlan.value = res.data.plan
      isSaved.value = true
    } else {
      message.error('行程数据格式不正确，可能需要重新规划行程')
    }
  } catch (error: any) {
    message.error('加载行程失败: ' + (error.response?.data?.detail || error.message || '未知错误'))
  }
}

const handleSaveTrip = async () => {
  if (!tripPlan.value || isSaved.value || savingTrip.value) return
  savingTrip.value = true
  try {
    const formData = sessionStorage.getItem('tripFormData')
    const request = formData ? JSON.parse(formData) : undefined
    await saveTripToHistory(tripPlan.value, request)
    isSaved.value = true
    message.success('行程已保存到我的行程！')
  } catch (e: any) {
    message.error('保存失败：' + (e.message || '未知错误'))
  } finally {
    savingTrip.value = false
  }
}

const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return
  const promises: Promise<void>[] = []
  tripPlan.value.days.forEach(day => {
    day.attractions.forEach(attraction => {
      if (attraction.image_url) {
        attractionPhotos.value[attraction.name] = attraction.image_url
        return
      }
      const promise = fetch(`/api/poi/photo?name=${encodeURIComponent(attraction.name)}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data.photo_url) {
            attractionPhotos.value[attraction.name] = data.data.photo_url
          }
        })
        .catch(() => {})
      promises.push(promise)
    })
  })
  await Promise.all(promises)
}

const exportDisclosures = () => Array.from(tabContentRef.value?.querySelectorAll('details') || []).map(node => ({node, open: node.open}))
async function restoreReadingState(disclosures: ReturnType<typeof exportDisclosures>) {
  isExporting.value = false
  await nextTick()
  disclosures.forEach(({node, open}) => { node.open = open })
}
const exportAsImage = async () => {
  if (isExporting.value) return
  const disclosures = exportDisclosures()
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })
    isExporting.value = true
    await nextTick()
    await tabMapRef.value?.prepareForExport?.()
    const element = tabContentRef.value
    if (!element) throw new Error('未找到内容元素')
    const canvas = await html2canvas(element, { backgroundColor: getComputedStyle(document.documentElement).getPropertyValue('--color-bg-primary').trim() || '#fcfbf8', scale: 2, logging: false, useCORS: true, allowTaint: true })
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  } finally {
    await restoreReadingState(disclosures)
  }
}

const exportAsPDF = async () => {
  if (isExporting.value) return
  const disclosures = exportDisclosures()
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })
    isExporting.value = true
    await nextTick()
    await tabMapRef.value?.prepareForExport?.()
    const element = tabContentRef.value
    if (!element) throw new Error('未找到内容元素')
    const canvas = await html2canvas(element, { backgroundColor: getComputedStyle(document.documentElement).getPropertyValue('--color-bg-primary').trim() || '#fcfbf8', scale: 2, logging: false, useCORS: true, allowTaint: true })
    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    const imgWidth = 210
    const imgHeight = (canvas.height * imgWidth) / canvas.width
    let heightLeft = imgHeight
    let position = 0
    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= 297
    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= 297
    }
    pdf.save(`旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.pdf`)
    message.success({ content: 'PDF导出成功!', key: 'export' })
  } catch (error: any) {
    message.error({ content: `导出PDF失败: ${error.message}`, key: 'export' })
  } finally {
    await restoreReadingState(disclosures)
  }
}
</script>

<style scoped>
.result-container { overflow-anchor: none; min-height: 100vh; color: var(--color-text-primary); padding: 0 28px 64px; max-width: 1240px; margin: auto; }
.result-hero { padding: 30px 0 24px; background: transparent !important; }
.hero-content { width: 100%; }
.result-back { padding: 0; margin-bottom: 26px; border: 0; background: none; color: var(--color-text-secondary); cursor: pointer; }
.result-eyebrow { color: var(--color-primary); font-size: 11px; letter-spacing: .18em; margin: 0 0 12px; }
.hero-title { margin: 0 0 10px; font-weight: 500; line-height: 1.3; letter-spacing: -.04em; }
.result-meta { color: var(--color-text-secondary); margin: 0 0 20px; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.hero-btn { padding: 8px 14px; font-size: 12px; cursor: pointer; border: 1px solid var(--color-border); border-radius: 9px; background: var(--color-bg-primary); }
.hero-btn:disabled { cursor: default; opacity: .65; }
.stats-section { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); padding: 20px 0; border-block: 1px solid var(--color-border); background: transparent !important; }
.stat-item { padding: 0 20px; border-right: 1px solid var(--color-border); min-width: 0; }
.stat-item:first-child { padding-left: 0; }
.stat-item:last-child { border: 0; }
.stat-value { font-size: clamp(20px,3vw,30px); overflow-wrap: anywhere; line-height: 1.3; }
.stat-label { margin-top: 6px; }
.stat-divider { display: none; }
.tab-bar { position: sticky; top: 64px; z-index: 100; padding: 10px 0; margin-bottom: 18px; background: var(--color-bg-primary) !important; border-bottom: 1px solid var(--color-border); box-shadow: 0 8px 18px #00000006; }
.tab-bar-inner { display: flex; gap: 8px; padding: 2px; }
.tab-pill { display: flex; align-items: center; gap: 8px; white-space: nowrap; min-height: 44px; padding: 11px 14px; cursor: pointer; border: 1px solid transparent; border-radius: 10px; background: transparent; transition: background .2s, color .2s; }
.tab-icon { font-size: 10px; opacity: .7; font-variant-numeric: tabular-nums; }
.tab-label { font-size: 13px; }
.tab-content { min-height: 360px; }
.is-exporting .tab-content > * + * { margin-top: 20px; }
.result-panel.is-active { animation: reading-panel-in .2s ease both; }
.is-exporting .result-panel { animation: none; }
@keyframes reading-panel-in { from { opacity: .4; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
.back-top-button { border-radius: 50%; background: var(--color-bg-primary); color: var(--color-text-primary); border: 1px solid var(--color-border); width: 40px; height: 40px; text-align: center; line-height: 38px; }
button:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 3px; }
.result-skeleton,.streaming-error { padding: 40px 0; }
.hero-skeleton,.cards-skeleton { padding: 24px; background: var(--color-bg-primary); border-radius: 18px; margin: 16px 0; }
.skeleton-hint { color: var(--color-text-secondary); }
@media(max-width:600px) {
  .result-container { padding: 0 16px 40px; }
  .result-hero { padding: 22px 0; }
  .result-back { margin-bottom: 20px; }
  .stats-section { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px 0; }
  .stat-item { padding: 0 14px; }
  .stat-item:nth-of-type(5) { padding-left: 0; }
  .stat-item:nth-of-type(3) { border: 0; }
  .tab-bar-inner { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 6px; }
  .tab-pill { padding: 10px 6px; justify-content: center; }
  .tab-icon { display: none; }
}
@media(prefers-reduced-motion:reduce) { .result-panel.is-active { animation: none; } .tab-pill { transition: none; } }
</style>
