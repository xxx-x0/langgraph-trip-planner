<template>
  <div class="tab-map">
    <div class="glass-card map-card">
      <div class="card-header">
        <span class="card-icon">📍</span>
        <span class="card-title">景点地图</span>
      </div>
      <div class="map-body">
        <div id="amap-container" class="map-container"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import type { TripPlan } from '@/types'

const props = defineProps<{
  tripPlan: TripPlan
  attractionPhotos: Record<string, string>
  visible: boolean
}>()

let map: any = null
const mapInitialized = ref(false)

watch(() => props.visible, async (val) => {
  if (val) {
    await nextTick()
    if (!mapInitialized.value) {
      initMap()
      mapInitialized.value = true
    } else if (map) {
      map.resize?.()
    }
  }
}, { immediate: true })

onBeforeUnmount(() => {
  if (map) {
    map.destroy()
    map = null
  }
})

const escapeHtml = (str: string | undefined | null): string => {
  if (str == null) return ''
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;')
}

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '小吃' }
  return labels[type] || type
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
  } catch (error) {
    console.error('地图加载失败:', error)
  }
}

const addAttractionMarkers = (AMap: any) => {
  if (!props.tripPlan) return
  const markers: any[] = []
  const allAttractions: any[] = []

  props.tripPlan.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction) => {
      if (attraction.location && attraction.location.longitude && attraction.location.latitude) {
        allAttractions.push({ ...attraction, dayIndex })
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
  props.tripPlan.days.forEach((day) => {
    day.meals.forEach((meal) => {
      if (meal.location && meal.location.longitude && meal.location.latitude) {
        allMeals.push(meal)
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
  props.tripPlan.days.forEach((day) => {
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
      path, strokeColor: '#667eea', strokeWeight: 4, strokeOpacity: 0.8, strokeStyle: 'solid', showDir: true
    })
    map.add(polyline)
  })
}

const refreshMap = () => {
  if (map) {
    map.destroy()
    map = null
    mapInitialized.value = false
    nextTick(() => {
      initMap()
      mapInitialized.value = true
    })
  }
}

defineExpose({ refreshMap })
</script>

<style scoped>
.tab-map {
  animation: fadeInUp var(--transition-normal);
}

.glass-card {
  background: var(--color-glass-bg);
  backdrop-filter: blur(var(--blur-glass));
  -webkit-backdrop-filter: blur(var(--blur-glass));
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  background: var(--color-gradient);
  color: #fff;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.card-icon {
  font-size: var(--font-size-xl);
}

.map-body {
  height: 600px;
}

.map-container {
  width: 100%;
  height: 100%;
}

@media (max-width: 768px) {
  .map-body {
    height: 400px;
  }
}
</style>
