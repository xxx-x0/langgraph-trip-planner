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
.tab-weather {
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

.weather-body {
  padding: var(--space-5);
}

.weather-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-4);
}

@media (max-width: 768px) {
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
