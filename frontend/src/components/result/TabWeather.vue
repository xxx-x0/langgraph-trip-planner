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

/* Bauhaus card styling */
.glass-card {
  background: var(--white);
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-6);
  background: var(--primary-yellow);
  color: var(--foreground);
  border-bottom: var(--border-main) solid var(--border);
}

.card-title {
  font-size: var(--text-xl);
  font-weight: var(--font-black);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.card-icon {
  font-size: var(--text-2xl);
}

.weather-body {
  padding: var(--space-6);
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
