<template>
  <div class="tab-weather">
    <div class="glass-card">
      <div class="card-header">
        <span class="card-icon">🌤️</span>
        <span class="card-title">天气信息</span>
      </div>
      <div class="weather-body">
        <div class="weather-grid">
          <WeatherCard v-for="w in weatherInfo" :key="w.date" :weather="w" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { WeatherInfo } from '@/types'
import WeatherCard from '@/components/WeatherCard.vue'

defineProps<{
  weatherInfo: WeatherInfo[]
}>()
</script>

<style scoped>
.glass-card { background: var(--color-bg-primary); color: var(--color-text-primary); border: 1px solid var(--color-border); border-radius: 18px; overflow: hidden; }
.card-header { padding: 24px; border-bottom: 1px solid var(--color-border); }.card-icon { display: none; }.card-title { font-size: 24px; font-weight: 500; }
.weather-body,.map-body { padding: 24px; }.weather-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 16px; }.map-container { width: 100%; height: 520px; border-radius: 12px; overflow: hidden; }
@media(max-width:600px) { .card-header { padding: 20px 18px; }.weather-body,.map-body { padding: 16px; }.map-container { height: 420px; } }
</style>
