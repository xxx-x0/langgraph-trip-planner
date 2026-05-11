<template>
  <div
    class="selectable-card-wrapper"
    :class="{ selected: attraction.selected }"
    @click="$emit('toggle', attraction)"
  >
    <div class="selection-checkbox">
      <div class="checkbox-inner" :class="{ checked: attraction.selected }">
        <span v-if="attraction.selected" class="check-icon">✓</span>
      </div>
    </div>
    <div v-if="attraction.manuallyAdded" class="manual-badge">手动添加</div>
    <div class="card-content">
      <div class="card-image" :style="{ backgroundImage: `url(${imageUrl})` }">
        <div v-if="attraction.ticket_price" class="price-tag">¥{{ attraction.ticket_price }}</div>
        <div v-if="attraction.category" class="category-tag">{{ attraction.category }}</div>
      </div>
      <div class="card-body">
        <h4 class="card-name">{{ attraction.name }}</h4>
        <div class="card-meta">
          <span v-if="attraction.rating" class="rating">
            <span class="star">★</span> {{ attraction.rating }}
          </span>
          <span v-if="attraction.address" class="address">{{ attraction.address }}</span>
        </div>
        <p v-if="attraction.description" class="card-desc">{{ attraction.description }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DiscoveredAttraction } from '@/types'

const props = defineProps<{
  attraction: DiscoveredAttraction
  photoUrl?: string
}>()

defineEmits<{
  toggle: [attraction: DiscoveredAttraction]
}>()

const gradientColors = ['#667eea,#764ba2', '#f093fb,#f5576c', '#4facfe,#00f2fe', '#43e97b,#38f9d7', '#fa709a,#fee140']

const imageUrl = computed(() => {
  if (props.photoUrl) return props.photoUrl
  if (props.attraction.image_url) return props.attraction.image_url
  const idx = props.attraction.name.length % gradientColors.length
  const colors = gradientColors[idx]
  const name = props.attraction.name.slice(0, 4)
  return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="300" height="160"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:${colors.split(',')[0]}"/><stop offset="100%" style="stop-color:${colors.split(',')[1]}"/></linearGradient></defs><rect width="300" height="160" fill="url(#g)"/><text x="150" y="88" text-anchor="middle" fill="white" font-size="28" font-family="sans-serif">${name}</text></svg>`)}`
})
</script>

<style scoped>
.selectable-card-wrapper {
  position: relative;
  border-radius: var(--radius-lg, 12px);
  background: var(--color-bg-elevated, #fff);
  border: 2px solid transparent;
  box-shadow: var(--shadow-card, 0 2px 8px rgba(0,0,0,0.08));
  cursor: pointer;
  transition: all var(--transition-normal, 0.3s) ease;
  overflow: hidden;
}

.selectable-card-wrapper:hover {
  box-shadow: var(--shadow-card-hover, 0 4px 16px rgba(0,0,0,0.12));
  transform: translateY(-2px);
}

.selectable-card-wrapper.selected {
  border-color: var(--color-primary, #667eea);
  box-shadow: 0 0 0 1px var(--color-primary, #667eea), var(--shadow-card-hover, 0 4px 16px rgba(0,0,0,0.12));
}

.selection-checkbox {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
}

.checkbox-inner {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.8);
  background: rgba(0,0,0,0.2);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.checkbox-inner.checked {
  background: var(--color-primary, #667eea);
  border-color: var(--color-primary, #667eea);
}

.check-icon {
  color: white;
  font-size: 14px;
  font-weight: bold;
}

.manual-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  padding: 2px 8px;
  border-radius: var(--radius-pill, 9999px);
  background: var(--color-accent, #764ba2);
  color: white;
  font-size: 11px;
}

.card-image {
  width: 100%;
  height: 140px;
  background-size: cover;
  background-position: center;
  position: relative;
}

.price-tag {
  position: absolute;
  top: 36px;
  right: 8px;
  padding: 2px 8px;
  border-radius: var(--radius-sm, 6px);
  background: rgba(245, 87, 108, 0.9);
  color: white;
  font-size: 12px;
  font-weight: 600;
}

.category-tag {
  position: absolute;
  bottom: 8px;
  left: 8px;
  padding: 2px 8px;
  border-radius: var(--radius-pill, 9999px);
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  color: white;
  font-size: 11px;
}

.card-body {
  padding: 10px 12px;
}

.card-name {
  margin: 0;
  font-size: var(--font-size-sm, 14px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.star {
  color: #faad14;
}

.address {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.card-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
