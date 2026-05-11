<template>
  <div class="discovery-map-container">
    <div id="discovery-map" ref="mapContainer"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import type { DiscoveredAttraction } from '@/types'

const props = defineProps<{
  attractions: DiscoveredAttraction[]
  highlightedName?: string
}>()

const emit = defineEmits<{
  markerClick: [attraction: DiscoveredAttraction]
}>()

const mapContainer = ref<HTMLElement>()
let map: any = null
let AMap: any = null
let markers: any[] = []
let infoWindow: any = null
const mapReady = ref(false)

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

async function initMap() {
  try {
    const AMapLoader = (await import('@amap/amap-jsapi-loader')).default
    AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY || '',
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.InfoWindow'],
    })

    map = new AMap.Map('discovery-map', {
      zoom: 12,
      center: [116.397128, 39.916527],
      viewMode: '2D',
    })

    infoWindow = new AMap.InfoWindow({
      offset: new AMap.Pixel(0, -30),
      closeWhenClickMap: true,
    })

    mapReady.value = true
    if (props.attractions.length > 0) {
      syncMarkers()
    }
  } catch (e) {
    console.error('地图初始化失败:', e)
  }
}

function syncMarkers() {
  if (!map || !AMap) return

  for (const m of markers) {
    map.remove(m)
  }
  markers = []

  let idx = 0
  for (const attr of props.attractions) {
    if (!attr.location?.longitude || !attr.location?.latitude) continue
    idx++

    const marker = new AMap.Marker({
      position: [attr.location.longitude, attr.location.latitude],
      label: {
        content: `<div style="
          background: ${attr.selected ? '#667eea' : '#999'};
          color: white;
          border-radius: 50%;
          width: 26px;
          height: 26px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: bold;
          box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        ">${idx}</div>`,
        direction: 'center',
      },
      offset: new AMap.Pixel(-13, -13),
    })

    const content = `<div style="padding:8px;min-width:180px;max-width:280px;">
      <h4 style="margin:0 0 4px;font-size:14px;">${escapeHtml(attr.name)}</h4>
      ${attr.category ? `<span style="display:inline-block;padding:1px 6px;border-radius:10px;background:#f0f0f0;font-size:11px;margin-bottom:4px;">${escapeHtml(attr.category)}</span>` : ''}
      ${attr.address ? `<p style="margin:2px 0;font-size:12px;color:#666;">${escapeHtml(attr.address)}</p>` : ''}
      ${attr.rating ? `<p style="margin:2px 0;font-size:12px;">★ ${attr.rating}</p>` : ''}
      ${attr.description ? `<p style="margin:2px 0;font-size:12px;color:#888;">${escapeHtml(attr.description).slice(0, 80)}</p>` : ''}
    </div>`

    marker.on('click', () => {
      infoWindow.setContent(content)
      infoWindow.open(map, marker.getPosition())
      emit('markerClick', attr)
    })

    markers.push(marker)
    map.add(marker)
  }

  if (markers.length > 0) {
    map.setFitView(markers, false, [60, 60, 60, 60])
  }
}

function panToAttraction(name: string) {
  if (!map || !AMap) return
  const attr = props.attractions.find(a => a.name === name)
  if (attr?.location) {
    map.setCenter([attr.location.longitude, attr.location.latitude])
    map.setZoom(15)
  }
}

watch(() => props.attractions, () => {
  if (mapReady.value) syncMarkers()
}, { deep: true })

watch(() => props.highlightedName, (name) => {
  if (name) panToAttraction(name)
})

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  if (map) {
    map.destroy()
    map = null
  }
})

defineExpose({ panToAttraction, syncMarkers })
</script>

<style scoped>
.discovery-map-container {
  width: 100%;
  height: 100%;
  min-height: 400px;
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
}

#discovery-map {
  width: 100%;
  height: 100%;
}
</style>
