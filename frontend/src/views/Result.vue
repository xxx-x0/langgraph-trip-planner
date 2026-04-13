<template>
  <div class="result-container">
    <div class="page-header">
      <a-button class="back-button" size="large" @click="goBack">
        ← 返回首页
      </a-button>
      <a-space size="middle">
        <a-button v-if="!isSaved" @click="handleSaveTrip" type="primary" ghost :loading="savingTrip">
          💾 保存到我的行程
        </a-button>
        <a-button v-else type="default" disabled>
          ✅ 已保存
        </a-button>
        <a-button v-if="!editMode" @click="toggleEditMode" type="default">
          ✏️ 编辑行程
        </a-button>
        <a-button v-else @click="saveChanges" type="primary">
          💾 保存修改
        </a-button>
        <a-button v-if="editMode" @click="cancelEdit" type="default">
          ❌ 取消编辑
        </a-button>
        <a-dropdown v-if="!editMode">
          <template #overlay>
            <a-menu>
              <a-menu-item key="image" @click="exportAsImage">📷 导出为图片</a-menu-item>
              <a-menu-item key="pdf" @click="exportAsPDF">📄 导出为PDF</a-menu-item>
            </a-menu>
          </template>
          <a-button type="default">📥 导出行程 <DownOutlined /></a-button>
        </a-dropdown>
      </a-space>
    </div>

    <div v-if="tripPlan" class="content-wrapper">
      <div class="side-nav">
        <a-affix :offset-top="80">
          <div class="side-nav-inner">
            <div class="nav-brand">{{ tripPlan.city }}旅行计划</div>
            <a-menu mode="inline" :selected-keys="[activeSection]" @click="scrollToSection">
              <a-menu-item key="overview"><span>📋 行程概览</span></a-menu-item>
              <a-menu-item key="budget" v-if="tripPlan.budget"><span>💰 预算明细</span></a-menu-item>
              <a-menu-item key="map"><span>📍 景点地图</span></a-menu-item>
              <a-sub-menu key="days" title="📅 每日行程">
                <a-menu-item v-for="(day, index) in tripPlan.days" :key="`day-${index}`">
                  第{{ day.day_index + 1 }}天
                </a-menu-item>
              </a-sub-menu>
              <a-menu-item key="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0">
                <span>🌤️ 天气信息</span>
              </a-menu-item>
            </a-menu>
          </div>
        </a-affix>
      </div>

      <div class="main-content">
        <div class="top-info-section">
          <div class="left-info">
            <a-card id="overview" :bordered="false" class="overview-card">
              <template #title>
                <div class="card-title-row">
                  <span class="card-title-icon">📋</span>
                  <span>{{ tripPlan.city }}旅行计划</span>
                </div>
              </template>
              <div class="overview-content">
                <div class="info-item">
                  <span class="info-label">📅 日期:</span>
                  <span class="info-value">{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span>
                </div>
                <div class="info-item" v-if="tripPlan.companions">
                  <span class="info-label">👥 出行信息:</span>
                  <span class="info-value">
                    {{ getCompanionLabel(tripPlan.companions.type) }} · {{ tripPlan.companions.count }}人
                  </span>
                </div>
                <div class="info-item">
                  <span class="info-label">💡 建议:</span>
                  <span class="info-value">{{ tripPlan.overall_suggestions }}</span>
                </div>
              </div>
            </a-card>

            <a-card id="budget" v-if="tripPlan.budget" :bordered="false" class="budget-card">
              <template #title>
                <div class="card-title-row">
                  <span class="card-title-icon">💰</span>
                  <span>预算明细</span>
                </div>
              </template>
              <div class="budget-grid">
                <div class="budget-item">
                  <div class="budget-label">景点门票</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_attractions }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">酒店住宿</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_hotels }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">餐饮费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_meals }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">交通费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_transportation }}</div>
                </div>
              </div>
              <div class="budget-total" :class="{ 'over-budget': tripPlan.budget.budget_limit && !tripPlan.budget.is_within_budget }">
                <span class="total-label">预估总费用</span>
                <span class="total-value">¥{{ tripPlan.budget.total }}</span>
              </div>
              <div v-if="tripPlan.budget.budget_limit" class="budget-limit-info">
                <div class="budget-limit-bar">
                  <div class="budget-limit-fill" :style="{ width: Math.min((tripPlan.budget.total / tripPlan.budget.budget_limit) * 100, 100) + '%' }" :class="{ 'over': tripPlan.budget.total > tripPlan.budget.budget_limit }"></div>
                </div>
                <div class="budget-limit-text">
                  <span>预算上限: ¥{{ tripPlan.budget.budget_limit }}</span>
                  <span :class="tripPlan.budget.is_within_budget ? 'within-budget' : 'over-budget-text'">
                    {{ tripPlan.budget.is_within_budget ? '✅ 在预算范围内' : '⚠️ 超出预算 ¥' + (tripPlan.budget.total - tripPlan.budget.budget_limit) }}
                  </span>
                </div>
              </div>
              <BudgetChart v-if="tripPlan.budget.total > 0" :budget="tripPlan.budget" class="budget-chart-section" />
            </a-card>
          </div>

          <div class="right-map">
            <a-card id="map" :bordered="false" class="map-card">
              <template #title>
                <div class="card-title-row">
                  <span class="card-title-icon">📍</span>
                  <span>景点地图</span>
                </div>
              </template>
              <div id="amap-container" style="width: 100%; height: 100%"></div>
            </a-card>
          </div>
        </div>

        <a-card :bordered="false" class="days-card">
          <template #title>
            <div class="card-title-row">
              <span class="card-title-icon">📅</span>
              <span>每日行程</span>
            </div>
          </template>
          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel v-for="(day, index) in tripPlan.days" :key="index" :id="`day-${index}`">
              <template #header>
                <div class="day-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                </div>
              </template>

              <div class="day-info">
                <div class="info-row">
                  <span class="label">📝 行程描述:</span>
                  <span class="value">{{ day.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🚗 交通方式:</span>
                  <span class="value">{{ day.transportation }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🏨 住宿:</span>
                  <span class="value">{{ day.accommodation }}</span>
                </div>
              </div>

              <a-divider orientation="left">⏰ 日程时间轴</a-divider>
              <DayTimeline :day="day" />

              <a-divider v-if="day.route_segments && day.route_segments.length > 0" orientation="left">🚦 路线规划</a-divider>
              <div v-if="day.route_segments && day.route_segments.length > 0" class="route-timeline">
                <div v-for="(segment, segIdx) in day.route_segments" :key="segIdx" class="route-segment">
                  <div class="route-segment-connector">
                    <div class="route-segment-dot" :class="getRouteModeClass(segment.mode)"></div>
                    <div v-if="segIdx < day.route_segments.length - 1" class="route-segment-line"></div>
                  </div>
                  <div class="route-segment-content">
                    <div class="route-segment-header">
                      <span class="route-from">{{ segment.from_name }}</span>
                      <span class="route-arrow">→</span>
                      <span class="route-to">{{ segment.to_name }}</span>
                      <a-tag :color="getRouteModeColor(segment.mode)" class="route-mode-tag">
                        {{ getRouteModeIcon(segment.mode) }} {{ segment.mode }}
                      </a-tag>
                    </div>
                    <div class="route-segment-meta">
                      <span v-if="segment.distance" class="route-meta-item">📏 {{ segment.distance }}</span>
                      <span v-if="segment.duration" class="route-meta-item">⏱️ {{ segment.duration }}</span>
                    </div>
                    <div v-if="segment.detail" class="route-segment-detail">{{ segment.detail }}</div>
                  </div>
                </div>
              </div>

              <a-divider orientation="left">🎯 景点安排</a-divider>
              <div class="attractions-grid">
                <AttractionCard
                  v-for="(item, attrIdx) in day.attractions"
                  :key="item.name + attrIdx"
                  :attraction="item"
                  :global-index="getAttractionGlobalIndex(day.day_index, attrIdx)"
                  :edit-mode="editMode"
                  :photo-url="attractionPhotos[item.name]"
                >
                  <template v-if="editMode" #extra>
                    <div class="attraction-actions">
                      <a-button size="small" @click="moveAttraction(day.day_index, attrIdx, 'up')" :disabled="attrIdx === 0">↑</a-button>
                      <a-button size="small" @click="moveAttraction(day.day_index, attrIdx, 'down')" :disabled="attrIdx === day.attractions.length - 1">↓</a-button>
                      <a-button size="small" danger @click="deleteAttraction(day.day_index, attrIdx)">🗑️</a-button>
                    </div>
                  </template>
                </AttractionCard>
              </div>

              <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
              <HotelCard v-if="day.hotel" :hotel="day.hotel" />

              <a-divider orientation="left">🍽️ 餐饮安排</a-divider>
              <div class="meals-section">
                <div v-if="day.meals.filter(m => m.source === 'nearby').length > 0" class="meals-group">
                  <div class="meals-group-title">📍 景点周边餐厅</div>
                  <div class="meals-grid">
                    <MealCard v-for="meal in day.meals.filter(m => m.source === 'nearby')" :key="meal.type + meal.name" :meal="meal" />
                  </div>
                </div>
                <div v-if="day.meals.filter(m => m.source === 'popular').length > 0" class="meals-group">
                  <div class="meals-group-title">🔥 城市热门餐厅</div>
                  <div class="meals-grid">
                    <MealCard v-for="meal in day.meals.filter(m => m.source === 'popular')" :key="meal.type + meal.name" :meal="meal" />
                  </div>
                </div>
                <div v-if="day.meals.filter(m => !m.source || (m.source !== 'nearby' && m.source !== 'popular')).length > 0" class="meals-group">
                  <div class="meals-group-title">🍽️ 餐饮推荐</div>
                  <div class="meals-grid">
                    <MealCard v-for="meal in day.meals.filter(m => !m.source || (m.source !== 'nearby' && m.source !== 'popular'))" :key="meal.type + meal.name" :meal="meal" />
                  </div>
                </div>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <a-card id="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0" :bordered="false" class="weather-section-card">
          <template #title>
            <div class="card-title-row">
              <span class="card-title-icon">🌤️</span>
              <span>天气信息</span>
            </div>
          </template>
          <div class="weather-grid">
            <WeatherCard v-for="w in tripPlan.weather_info" :key="w.date" :weather="w" />
          </div>
        </a-card>
      </div>
    </div>

    <a-empty v-else description="没有找到旅行计划数据">
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
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import type { TripPlan } from '@/types'
import BudgetChart from '@/components/BudgetChart.vue'
import DayTimeline from '@/components/DayTimeline.vue'
import AttractionCard from '@/components/AttractionCard.vue'
import HotelCard from '@/components/HotelCard.vue'
import MealCard from '@/components/MealCard.vue'
import WeatherCard from '@/components/WeatherCard.vue'
import { saveTripToHistory, getTripDetail } from '@/services/api'
import { useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const isSaved = ref(false)
const savingTrip = ref(false)

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

const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeSection = ref('overview')
const activeDays = ref<number[]>([0])
let map: any = null

onMounted(async () => {
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
    await nextTick()
    initMap()
  }
})

const goBack = () => { router.push('/') }

const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const toggleEditMode = () => {
  editMode.value = true
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

const saveChanges = () => {
  editMode.value = false
  if (tripPlan.value) {
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
  }
  message.success('修改已保存')
  if (map) { map.destroy() }
  nextTick(() => { initMap() })
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

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '小吃' }
  return labels[type] || type
}

const getCompanionLabel = (type: string): string => {
  const labels: Record<string, string> = {
    solo: '🧑 独自出行', couple: '💑 情侣出行', family: '👨‍👩‍👧 家庭亲子',
    friends: '👫 朋友出行', elderly: '👴 带老人出行', group: '👥 团队出行'
  }
  return labels[type] || type
}

const getRouteModeColor = (mode: string): string => {
  const colors: Record<string, string> = { '地铁': 'blue', '公交': 'green', '步行': 'orange', '驾车': 'red', '出租车': 'purple', '骑行': 'cyan' }
  return colors[mode] || 'default'
}

const getRouteModeIcon = (mode: string): string => {
  const icons: Record<string, string> = { '地铁': '🚇', '公交': '🚌', '步行': '🚶', '驾车': '🚗', '出租车': '🚕', '骑行': '🚲' }
  return icons[mode] || '🚗'
}

const getRouteModeClass = (mode: string): string => {
  const classes: Record<string, string> = { '地铁': 'mode-subway', '公交': 'mode-bus', '步行': 'mode-walk', '驾车': 'mode-drive', '出租车': 'mode-taxi', '骑行': 'mode-bike' }
  return classes[mode] || 'mode-default'
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

const getAttractionGlobalIndex = (dayIndex: number, attrIndex: number): number => {
  if (!tripPlan.value) return attrIndex + 1
  let count = 0
  for (let i = 0; i < dayIndex; i++) {
    count += tripPlan.value.days[i]?.attractions?.length || 0
  }
  return count + attrIndex + 1
}

const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })
    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) throw new Error('未找到内容元素')
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'
    exportContainer.innerHTML = element.innerHTML
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)
    const canvas = await html2canvas(exportContainer, { backgroundColor: '#f5f7fa', scale: 2, logging: false, useCORS: true, allowTaint: true })
    document.body.removeChild(exportContainer)
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

const exportAsPDF = async () => {
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })
    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) throw new Error('未找到内容元素')
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'
    exportContainer.innerHTML = element.innerHTML
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)
    const canvas = await html2canvas(exportContainer, { backgroundColor: '#f5f7fa', scale: 2, logging: false, useCORS: true, allowTaint: true })
    document.body.removeChild(exportContainer)
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
  }
}

const escapeHtml = (str: string | undefined | null): string => {
  if (str == null) return ''
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;')
}

const initMap = async () => {
  try {
    const AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow']
    })
    map = new AMap.Map('amap-container', {
      zoom: 12,
      center: [116.397128, 39.916527],
      viewMode: '3D'
    })
    addAttractionMarkers(AMap)
    message.success('地图加载成功')
  } catch (error) {
    console.error('地图加载失败:', error)
    message.error('地图加载失败')
  }
}

const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value) return
  const markers: any[] = []
  const allAttractions: any[] = []

  tripPlan.value.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction, attrIndex) => {
      if (attraction.location && attraction.location.longitude && attraction.location.latitude) {
        allAttractions.push({ ...attraction, dayIndex, attrIndex })
      }
    })
  })

  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: var(--color-primary, #667eea); color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })
    const infoWindow = new AMap.InfoWindow({
      content: `<div style="padding: 10px;"><h4 style="margin: 0 0 8px 0;">${escapeHtml(attraction.name)}</h4><p style="margin: 4px 0;"><strong>地址:</strong> ${escapeHtml(attraction.address)}</p><p style="margin: 4px 0;"><strong>游览时长:</strong> ${escapeHtml(String(attraction.visit_duration))}分钟</p><p style="margin: 4px 0;"><strong>描述:</strong> ${escapeHtml(attraction.description)}</p></div>`,
      offset: new AMap.Pixel(0, -30)
    })
    marker.on('click', () => { infoWindow.open(map, marker.getPosition()) })
    markers.push(marker)
  })

  const allMeals: any[] = []
  tripPlan.value.days.forEach((day, dayIndex) => {
    day.meals.forEach((meal, mealIndex) => {
      if (meal.location && meal.location.longitude && meal.location.latitude) {
        allMeals.push({ ...meal, dayIndex, mealIndex })
      }
    })
  })

  allMeals.forEach((meal) => {
    const isNearby = meal.source === 'nearby'
    const bgColor = isNearby ? '#67c23a' : '#f56c6c'
    const label = isNearby ? '📍' : '🔥'
    const marker = new AMap.Marker({
      position: [meal.location.longitude, meal.location.latitude],
      title: meal.name,
      label: {
        content: `<div style="background: ${bgColor}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap;">${label}${getMealLabel(meal.type)}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })
    const infoWindow = new AMap.InfoWindow({
      content: `<div style="padding: 10px; min-width: 200px;"><h4 style="margin: 0 0 8px 0;">${escapeHtml(meal.name)}</h4>${meal.cuisine ? `<p style="margin: 4px 0;"><strong>菜系:</strong> ${escapeHtml(meal.cuisine)}</p>` : ''}${meal.rating ? `<p style="margin: 4px 0;"><strong>评分:</strong> ⭐${escapeHtml(String(meal.rating))}</p>` : ''}${meal.avg_cost ? `<p style="margin: 4px 0;"><strong>人均:</strong> ¥${escapeHtml(String(meal.avg_cost))}</p>` : ''}</div>`,
      offset: new AMap.Pixel(0, -30)
    })
    marker.on('click', () => { infoWindow.open(map, marker.getPosition()) })
    markers.push(marker)
  })

  const addedHotels = new Set<string>()
  tripPlan.value.days.forEach((day, dayIndex) => {
    if (day.hotel && day.hotel.location && day.hotel.location.longitude && day.hotel.location.latitude) {
      const hotelKey = day.hotel.name
      if (addedHotels.has(hotelKey)) return
      addedHotels.add(hotelKey)
      const hotelMarker = new AMap.Marker({
        position: [day.hotel.location.longitude, day.hotel.location.latitude],
        title: day.hotel.name,
        label: {
          content: `<div style="background: #9C27B0; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap;">🏨${escapeHtml(day.hotel.name)}</div>`,
          offset: new AMap.Pixel(0, -30)
        }
      })
      const hotelInfoWindow = new AMap.InfoWindow({
        content: `<div style="padding: 10px; min-width: 200px;"><h4 style="margin: 0 0 8px 0;">🏨 ${escapeHtml(day.hotel.name)}</h4>${day.hotel.address ? `<p style="margin: 4px 0;"><strong>地址:</strong> ${escapeHtml(day.hotel.address)}</p>` : ''}${day.hotel.price_range ? `<p style="margin: 4px 0;"><strong>价格:</strong> ${escapeHtml(day.hotel.price_range)}</p>` : ''}</div>`,
        offset: new AMap.Pixel(0, -30)
      })
      hotelMarker.on('click', () => { hotelInfoWindow.open(map, hotelMarker.getPosition()) })
      markers.push(hotelMarker)
    }
  })

  map.add(markers)
  if (markers.length > 0) { map.setFitView(markers) }
  drawRoutes(AMap, allAttractions)
}

const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return
  const dayGroups: any = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) { dayGroups[attr.dayIndex] = [] }
    dayGroups[attr.dayIndex].push(attr)
  })
  Object.values(dayGroups).forEach((dayAttractions: any) => {
    if (dayAttractions.length < 2) return
    const path = dayAttractions.map((attr: any) => [attr.location.longitude, attr.location.latitude])
    const polyline = new AMap.Polyline({
      path: path, strokeColor: '#667eea', strokeWeight: 4, strokeOpacity: 0.8, strokeStyle: 'solid', showDir: true
    })
    map.add(polyline)
  })
}
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background: var(--color-bg-secondary);
  padding: var(--space-8) var(--space-6);
  transition: background var(--transition-normal);
}

.page-header {
  max-width: var(--content-max-width);
  margin: 0 auto var(--space-8);
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: fadeInDown var(--transition-normal);
}

.back-button {
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);
}

.content-wrapper {
  max-width: var(--content-max-width);
  margin: 0 auto;
  display: flex;
  gap: var(--space-6);
}

.side-nav {
  width: var(--side-nav-width);
  flex-shrink: 0;
}

.side-nav-inner {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
}

.nav-brand {
  padding: var(--space-4) var(--space-4) var(--space-2);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border-light);
}

.side-nav :deep(.ant-menu) {
  border-radius: 0 0 var(--radius-md) var(--radius-md);
  background: transparent;
  border: none;
}

.side-nav :deep(.ant-menu-item) {
  margin: 2px var(--space-2);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.side-nav :deep(.ant-menu-item-selected) {
  background: var(--color-gradient);
  color: var(--color-text-inverse);
}

.side-nav :deep(.ant-menu-item:hover) {
  background: var(--color-primary-bg);
}

.main-content {
  flex: 1;
  min-width: 0;
}

.top-info-section {
  display: flex;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
}

.left-info {
  flex: 0 0 400px;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.right-map {
  flex: 1;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.card-title-icon {
  font-size: var(--font-size-xl);
}

.overview-card,
.budget-card,
.map-card,
.days-card,
.weather-section-card {
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-card) !important;
  border: 1px solid var(--color-border-light) !important;
  background: var(--color-bg-elevated) !important;
  transition: box-shadow var(--transition-normal);
}

.overview-card:hover,
.budget-card:hover,
.days-card:hover,
.weather-section-card:hover {
  box-shadow: var(--shadow-card-hover) !important;
}

:deep(.ant-card-head) {
  background: var(--color-gradient);
  color: var(--color-text-inverse) !important;
  border-radius: var(--radius-md) var(--radius-md) 0 0 !important;
  border-bottom: none !important;
}

:deep(.ant-card-head-title) {
  color: var(--color-text-inverse) !important;
  font-size: var(--font-size-lg);
}

:deep(.ant-card-head-title span) {
  color: var(--color-text-inverse) !important;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.info-value {
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  line-height: var(--line-height-relaxed);
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.budget-item {
  text-align: center;
  padding: var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.budget-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}

.budget-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  background: var(--color-gradient);
  border-radius: var(--radius-sm);
  color: var(--color-text-inverse);
}

.budget-total.over-budget {
  background: linear-gradient(135deg, #ff4d4f 0%, #cf1322 100%);
}

.total-label {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.total-value {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
}

.budget-limit-info {
  margin-top: var(--space-3);
  padding: var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
}

.budget-limit-bar {
  height: 8px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-pill);
  overflow: hidden;
  margin-bottom: var(--space-2);
}

.budget-limit-fill {
  height: 100%;
  background: linear-gradient(90deg, #52c41a, #73d13d);
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}

.budget-limit-fill.over {
  background: linear-gradient(90deg, #ff4d4f, #cf1322);
}

.budget-limit-text {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.within-budget { color: var(--color-success); font-weight: var(--font-weight-semibold); }
.over-budget-text { color: var(--color-error); font-weight: var(--font-weight-semibold); }

.budget-chart-section {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
}

.map-card {
  height: 100%;
  min-height: 500px;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

.days-card {
  margin-top: var(--space-5);
}

:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-border) !important;
  border-radius: var(--radius-md) !important;
  overflow: hidden;
}

:deep(.ant-collapse-header) {
  background: var(--color-bg-secondary) !important;
  padding: var(--space-4) var(--space-5) !important;
  font-weight: var(--font-weight-semibold);
}

:deep(.ant-collapse-content) {
  border-top: 1px solid var(--color-border-light) !important;
}

:deep(.ant-collapse-content-box) {
  padding: var(--space-5);
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.day-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.day-date {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.day-info {
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
}

.info-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.info-row:last-child { margin-bottom: 0; }

.info-row .label {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  min-width: 100px;
}

.info-row .value {
  color: var(--color-text-primary);
  flex: 1;
}

.attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.attraction-actions {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.route-timeline {
  padding: var(--space-3) 0 var(--space-1);
}

.route-segment {
  display: flex;
  gap: var(--space-3);
  min-height: 60px;
}

.route-segment-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
}

.route-segment-dot {
  width: 14px;
  height: 14px;
  border-radius: var(--radius-circle);
  flex-shrink: 0;
  border: 2px solid var(--color-bg-elevated);
  background: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary);
}

.route-segment-dot.mode-subway { background: var(--color-route-subway); box-shadow: 0 0 0 2px var(--color-route-subway); }
.route-segment-dot.mode-bus { background: var(--color-route-bus); box-shadow: 0 0 0 2px var(--color-route-bus); }
.route-segment-dot.mode-walk { background: var(--color-route-walk); box-shadow: 0 0 0 2px var(--color-route-walk); }
.route-segment-dot.mode-drive { background: var(--color-route-drive); box-shadow: 0 0 0 2px var(--color-route-drive); }
.route-segment-dot.mode-taxi { background: var(--color-route-taxi); box-shadow: 0 0 0 2px var(--color-route-taxi); }
.route-segment-dot.mode-bike { background: var(--color-route-bike); box-shadow: 0 0 0 2px var(--color-route-bike); }
.route-segment-dot.mode-default { background: var(--color-text-disabled); box-shadow: 0 0 0 2px var(--color-text-disabled); }

.route-segment-line {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: linear-gradient(to bottom, rgba(102, 126, 234, 0.2), var(--color-primary));
  margin: var(--space-1) 0;
}

.route-segment-content {
  flex: 1;
  padding-bottom: var(--space-4);
}

.route-segment-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.route-from, .route-to {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}

.route-arrow {
  color: var(--color-text-tertiary);
  font-weight: var(--font-weight-bold);
}

.route-mode-tag { margin-left: var(--space-1); }

.route-segment-meta {
  display: flex;
  gap: var(--space-4);
  margin-top: 4px;
}

.route-meta-item {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.route-segment-detail {
  margin-top: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed);
  border-left: 3px solid var(--color-primary);
}

.meals-section { margin-top: var(--space-2); }

.meals-group { margin-bottom: var(--space-4); }
.meals-group:last-child { margin-bottom: 0; }

.meals-group-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-3);
  padding-left: var(--space-1);
}

.meals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-3);
}

.weather-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-4);
}

.weather-section-card {
  margin-top: var(--space-5);
}

.back-top-button {
  width: 48px;
  height: 48px;
  background: var(--color-gradient);
  color: var(--color-text-inverse);
  border-radius: var(--radius-circle);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  box-shadow: var(--shadow-button);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.back-top-button:hover {
  transform: scale(1.1);
  box-shadow: var(--shadow-button-hover);
}

@media (max-width: 1024px) {
  .top-info-section {
    flex-direction: column;
  }
  .left-info {
    flex: none;
  }
}

@media (max-width: 768px) {
  .result-container {
    padding: var(--space-4) var(--space-3);
  }

  .page-header {
    flex-direction: column;
    gap: var(--space-4);
  }

  .side-nav {
    display: none;
  }

  .attractions-grid {
    grid-template-columns: 1fr;
  }

  .meals-grid {
    grid-template-columns: 1fr;
  }

  .weather-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 480px) {
  .weather-grid {
    grid-template-columns: 1fr;
  }
}
</style>
