<template>
  <div class="result-container">
    <div v-if="isStreaming && skeletonStage === 'error'" class="streaming-error">
      <a-result status="error" :title="streamError || '生成失败'">
        <template #extra>
          <a-button type="primary" @click="onRetry">重试</a-button>
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

    <!-- Hero 区域 - 红色背景 -->
    <div v-if="tripPlan" class="result-hero" data-flip-id="loader-hero">
      <div class="hero-content">
        <h1 class="hero-title">{{ tripPlan.title || tripPlan.city + '旅行计划' }}</h1>
        <div class="hero-actions">
          <button class="hero-btn" @click="handleSaveTrip" :disabled="savingTrip">
            💾 {{ isSaved ? '已保存' : '保存行程' }}
          </button>
          <button class="hero-btn" @click="toggleEditMode" v-if="!editMode">
            ✏️ 编辑
          </button>
          <button class="hero-btn" @click="saveChanges" v-if="editMode">
            ✅ 保存修改
          </button>
          <button class="hero-btn" @click="cancelEdit" v-if="editMode">
            ❌ 取消
          </button>
          <button class="hero-btn" @click="exportAsImage">
            📥 导出图片
          </button>
          <button class="hero-btn" @click="exportAsPDF">
            📄 导出PDF
          </button>
        </div>
      </div>
    </div>

    <!-- 统计数据区 - 黄色背景 -->
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
        <div class="stat-value">¥{{ tripPlan.budget?.total || 0 }}</div>
        <div class="stat-label">预算</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-value">{{ transportLabel }}</div>
        <div class="stat-label">交通方式</div>
      </div>
    </div>

    <div v-if="tripPlan" class="tab-bar">
      <div class="tab-bar-inner">
        <button
          v-for="tab in visibleTabs"
          :key="tab.key"
          class="tab-pill"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <div v-if="tripPlan" class="tab-content" ref="tabContentRef">
      <Transition name="tab-fade" mode="out-in">
        <TabOverview v-if="activeTab === 'overview' || isExporting" :trip-plan="tripPlan" :key="'overview'" />
      </Transition>
      <Transition name="tab-fade" mode="out-in">
        <TabBudget v-if="(activeTab === 'budget' || isExporting) && tripPlan.budget" :budget="tripPlan.budget" :key="'budget'" />
      </Transition>
      <div v-show="activeTab === 'map' || isExporting">
        <TabMap
          ref="tabMapRef"
          :trip-plan="tripPlan"
          :attraction-photos="attractionPhotos"
          :visible="activeTab === 'map'"
        />
      </div>
      <Transition name="tab-fade" mode="out-in">
        <TabItinerary
          v-if="activeTab === 'itinerary' || isExporting"
          :trip-plan="tripPlan"
          :edit-mode="editMode"
          :attraction-photos="attractionPhotos"
          v-model:active-days="activeDays"
          @delete-attraction="deleteAttraction"
          @move-attraction="moveAttraction"
          :key="'itinerary'"
        />
      </Transition>
      <Transition name="tab-fade" mode="out-in">
        <TabWeather
          v-if="(activeTab === 'weather' || isExporting) && tripPlan.weather_info && tripPlan.weather_info.length > 0"
          :weather-info="tripPlan.weather_info"
          :key="'weather'"
        />
      </Transition>
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

const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeTab = ref('overview')
const activeDays = ref<number[]>([0])
const isSaved = ref(false)
const savingTrip = ref(false)
const isExporting = ref(false)
const tabContentRef = ref<HTMLElement | null>(null)
const tabMapRef = ref<InstanceType<typeof TabMap> | null>(null)

const totalAttractions = computed(() => {
  if (!tripPlan.value?.days) return 0
  return tripPlan.value.days.reduce((sum, day) => sum + (day.attractions?.length || 0), 0)
})

const transportLabel = computed(() => {
  if (!tripPlan.value) return '-'
  const transport = tripPlan.value.transport_mode || tripPlan.value.days?.[0]?.transport_mode || ''
  const labels: Record<string, string> = {
    'driving': '自驾',
    'transit': '公交',
    'walking': '步行',
    'bicycling': '骑行'
  }
  return labels[transport] || transport || '-'
})

const visibleTabs = computed(() => {
  const tabs = [{ key: 'overview', icon: '📋', label: '行程概览' }]
  if (tripPlan.value?.budget) tabs.push({ key: 'budget', icon: '💰', label: '预算明细' })
  tabs.push({ key: 'map', icon: '📍', label: '景点地图' })
  tabs.push({ key: 'itinerary', icon: '📅', label: '每日行程' })
  if (tripPlan.value?.weather_info?.length) tabs.push({ key: 'weather', icon: '🌤️', label: '天气信息' })
  return tabs
})

// 切换标签时回到顶部（标签栏已不再固定，避免停在上一个标签的滚动位置）
watch(activeTab, () => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
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
  const draftId = route.query.draft_id as string
  if (!draftId) {
    streamError.value = '缺少 draft_id'
    skeletonStage.value = 'error'
    return
  }
  streamError.value = null
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
  }
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
  if (!tripPlan.value) return
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

const toggleEditMode = () => {
  editMode.value = true
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  activeTab.value = 'itinerary'
  message.info('进入编辑模式')
}

const saveChanges = () => {
  editMode.value = false
  if (tripPlan.value) {
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
  }
  message.success('修改已保存')
  tabMapRef.value?.refreshMap()
}

const cancelEdit = () => {
  if (originalPlan.value) {
    tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  }
  editMode.value = false
  message.info('已取消编辑')
}

const deleteAttraction = (dayIndex: number, attrIndex: number) => {
  if (!tripPlan.value) return
  const day = tripPlan.value.days[dayIndex]
  if (day.attractions.length <= 1) {
    message.warning('每天至少需要保留一个景点')
    return
  }
  day.attractions.splice(attrIndex, 1)
  message.success('景点已删除')
}

const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return
  const day = tripPlan.value.days[dayIndex]
  const attractions = day.attractions
  if (direction === 'up' && attrIndex > 0) {
    [attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    [attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
}

const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return
  const promises: Promise<void>[] = []
  tripPlan.value.days.forEach(day => {
    day.attractions.forEach(attraction => {
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

const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })
    isExporting.value = true
    await nextTick()
    const element = tabContentRef.value
    if (!element) throw new Error('未找到内容元素')
    const canvas = await html2canvas(element, { backgroundColor: '#f5f7fa', scale: 2, logging: false, useCORS: true, allowTaint: true })
    isExporting.value = false
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    isExporting.value = false
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

const exportAsPDF = async () => {
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })
    isExporting.value = true
    await nextTick()
    const element = tabContentRef.value
    if (!element) throw new Error('未找到内容元素')
    const canvas = await html2canvas(element, { backgroundColor: '#f5f7fa', scale: 2, logging: false, useCORS: true, allowTaint: true })
    isExporting.value = false
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
    isExporting.value = false
    message.error({ content: `导出PDF失败: ${error.message}`, key: 'export' })
  }
}
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background: var(--background);
}

.streaming-error {
  padding: 80px 16px;
}

/* SSE 期间的骨架屏 */
.result-skeleton {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 16px;
}

.hero-skeleton {
  padding: 48px 24px;
  margin-bottom: 32px;
  background: var(--background-secondary, #fafafa);
  border-radius: 16px;
  text-align: center;
}

.skeleton-hint {
  margin-top: 16px;
  color: var(--color-text-secondary, #888);
  font-size: 14px;
}

.cards-skeleton {
  display: grid;
  gap: 24px;
  grid-template-columns: 1fr;
}

.cards-skeleton :deep(.ant-skeleton) {
  padding: 16px;
  background: var(--background-secondary, #fafafa);
  border-radius: 12px;
}

/* Hero 区域 - 红色背景 */
.result-hero {
  background: var(--primary-red);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-12) var(--space-6);
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.hero-content {
  max-width: 1200px;
  width: 100%;
  text-align: center;
}

.hero-title {
  color: var(--white);
  font-size: var(--text-6xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  margin-bottom: var(--space-6);
  text-shadow: 4px 4px 0px rgba(0, 0, 0, 0.2);
}

.hero-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  flex-wrap: wrap;
}

.hero-btn {
  background: transparent;
  color: var(--white);
  border: var(--border-main) solid var(--white);
  padding: 12px 24px;
  font-family: var(--font-family);
  font-weight: var(--font-black);
  font-size: var(--text-base);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 3px 3px 0px 0px var(--white);
}

.hero-btn:hover:not(:disabled) {
  background: var(--white);
  color: var(--primary-red);
}

.hero-btn:active:not(:disabled) {
  transform: translate(2px, 2px);
  box-shadow: none;
}

.hero-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 统计数据区 - 黄色背景 */
.stats-section {
  background: var(--primary-yellow);
  border-bottom: var(--border-main) solid var(--border);
  display: flex;
  height: 80px;
  align-items: center;
  justify-content: center;
}

.stat-item {
  flex: 1;
  text-align: center;
  padding: var(--space-4);
}

.stat-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-black);
  color: var(--foreground);
  margin-bottom: var(--space-1);
}

.stat-label {
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  color: var(--foreground);
  text-transform: uppercase;
}

.stat-divider {
  width: var(--border-main);
  height: 60%;
  background: var(--border);
}

/* Tab 导航 - 包豪斯风格 */
.tab-bar {
  background: var(--white);
  border-bottom: var(--border-main) solid var(--border);
  padding: var(--space-4) var(--space-6);
}

.tab-bar-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  gap: var(--space-2);
  justify-content: center;
}

.tab-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 24px;
  border: var(--border-main) solid var(--border);
  background: var(--white);
  color: var(--foreground);
  font-size: var(--text-base);
  font-weight: var(--font-black);
  font-family: var(--font-family);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
  box-shadow: 3px 3px 0px 0px var(--border);
}

.tab-pill:hover {
  background: var(--primary-yellow);
  transform: translate(-1px, -1px);
  box-shadow: 4px 4px 0px 0px var(--border);
}

.tab-pill:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

.tab-pill.active {
  background: var(--primary-blue);
  color: var(--white);
}

.tab-icon {
  font-size: var(--text-base);
}

/* 内容区 */
.tab-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-6);
}

/* 所有卡片统一包豪斯样式 */
:deep(.ant-card) {
  background: var(--white) !important;
  border: var(--border-main) solid var(--border) !important;
  border-radius: 0 !important;
  box-shadow: var(--shadow-main) !important;
  margin-bottom: var(--space-6) !important;
}

:deep(.ant-card-head) {
  border-bottom: var(--border-main) solid var(--border) !important;
  background: transparent !important;
}

:deep(.ant-card-head-title) {
  font-weight: var(--font-black) !important;
  text-transform: uppercase !important;
  font-size: var(--text-xl) !important;
}

/* 返回顶部按钮 */
.back-top-button {
  width: 48px;
  height: 48px;
  background: var(--primary-blue);
  color: var(--white);
  border: var(--border-2) solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  box-shadow: var(--shadow-md);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.back-top-button:hover {
  background: var(--primary-yellow);
  color: var(--foreground);
  transform: translate(-2px, -2px);
  box-shadow: 4px 4px 0px 0px var(--border);
}

.back-top-button:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

/* 移动端适配 */
@media (max-width: 640px) {
  .result-hero {
    min-height: 150px;
    padding: var(--space-8) var(--space-4);
  }

  .hero-title {
    font-size: var(--text-3xl);
  }

  .hero-btn {
    padding: 10px 20px;
    font-size: var(--text-sm);
  }

  .stats-section {
    flex-wrap: wrap;
    height: auto;
  }

  .stat-item {
    flex: 0 0 50%;
    border-bottom: var(--border-2) solid var(--border);
  }

  .stat-item:nth-child(1),
  .stat-item:nth-child(3) {
    border-right: var(--border-2) solid var(--border);
  }

  .stat-divider {
    display: none;
  }

  .tab-bar {
    padding: var(--space-3) var(--space-4);
    overflow-x: auto;
  }

  .tab-bar-inner {
    justify-content: flex-start;
  }

  .tab-pill {
    padding: 10px 16px;
    font-size: var(--text-sm);
  }

  .tab-content {
    padding: var(--space-4);
  }

  :deep(.ant-card) {
    margin-bottom: var(--space-4) !important;
  }
}

@media (max-width: 480px) {
  .tab-label {
    display: none;
  }
}
</style>
