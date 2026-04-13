<template>
  <div class="weather-card">
    <div class="weather-date">{{ weather.date }}</div>
    <div class="weather-main">
      <span class="weather-emoji">{{ getWeatherEmoji(weather.day_weather) }}</span>
      <div class="weather-info">
        <div class="weather-temp">
          <span class="temp-value">{{ weather.day_temp }}</span>
          <span class="temp-unit">°C</span>
        </div>
        <div class="weather-condition">{{ weather.day_weather }}</div>
      </div>
    </div>
    <div class="weather-night">
      <span class="night-label">夜间</span>
      <span class="night-weather">{{ weather.night_weather }}</span>
      <span class="night-temp">{{ weather.night_temp }}°C</span>
    </div>
    <div class="weather-details">
      <div class="detail-item">
        <span class="detail-icon">💨</span>
        <span class="detail-value">{{ weather.wind_direction }} {{ weather.wind_power }}</span>
      </div>
    </div>
    <div class="temp-bar-wrapper">
      <div class="temp-bar" :style="tempBarStyle"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WeatherInfo } from '@/types'

const props = defineProps<{
  weather: WeatherInfo
}>()

const getWeatherEmoji = (condition: string): string => {
  if (!condition) return '🌤️'
  const c = condition.toLowerCase()
  if (c.includes('晴')) return '☀️'
  if (c.includes('云') || c.includes('阴')) return '☁️'
  if (c.includes('雨')) return '🌧️'
  if (c.includes('雪')) return '❄️'
  if (c.includes('雷')) return '⛈️'
  if (c.includes('雾') || c.includes('霾')) return '🌫️'
  return '🌤️'
}

const tempBarStyle = computed(() => {
  const temp = Number(props.weather.day_temp) || 20
  const percent = Math.min(100, Math.max(0, ((temp + 10) / 50) * 100))
  let color = '#43e97b'
  if (temp < 5) color = '#4facfe'
  else if (temp < 15) color = '#43e97b'
  else if (temp < 25) color = '#faad14'
  else if (temp < 35) color = '#fa8c16'
  else color = '#f5222d'
  return {
    width: `${percent}%`,
    background: color,
  }
})
</script>

<style scoped>
.weather-card {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  box-shadow: var(--shadow-card);
  border: 1px solid var(--color-border-light);
}

.weather-date {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-2);
}

.weather-main {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.weather-emoji {
  font-size: var(--font-size-5xl);
  line-height: 1;
}

.weather-info {
  flex: 1;
}

.weather-temp {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.temp-value {
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  line-height: 1;
}

.temp-unit {
  font-size: var(--font-size-lg);
  color: var(--color-text-tertiary);
}

.weather-condition {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: 4px;
}

.weather-night {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
}

.night-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.night-weather {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.night-temp {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-left: auto;
}

.weather-details {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.detail-icon {
  font-size: var(--font-size-sm);
}

.detail-value {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.temp-bar-wrapper {
  height: 4px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

.temp-bar {
  height: 100%;
  border-radius: var(--radius-pill);
  transition: width var(--transition-slow), background var(--transition-slow);
}
</style>
