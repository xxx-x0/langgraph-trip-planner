<template>
  <div class="attraction-card" :class="{ 'edit-mode': editMode }">
    <div class="attraction-image-wrapper">
      <img
        :src="imageUrl"
        :alt="attraction.name"
        class="attraction-image"
        @error="handleImageError"
      />
      <div class="attraction-badge">
        <span class="badge-number">{{ globalIndex }}</span>
      </div>
      <div v-if="attraction.ticket_price" class="price-tag">
        ¥{{ attraction.ticket_price }}
      </div>
      <div v-if="attraction.category" class="category-tag">
        {{ attraction.category }}
      </div>
    </div>
    <div class="attraction-body">
      <template v-if="editMode">
        <div class="edit-field">
          <label>地址</label>
          <a-input v-model:value="attraction.address" size="small" />
        </div>
        <div class="edit-field">
          <label>游览时长(分钟)</label>
          <a-input-number v-model:value="attraction.visit_duration" :min="10" :max="480" size="small" style="width: 100%" />
        </div>
        <div class="edit-field">
          <label>描述</label>
          <a-textarea v-model:value="attraction.description" :rows="2" size="small" />
        </div>
      </template>
      <template v-else>
        <h4 class="attraction-name">{{ attraction.name }}</h4>
        <div class="attraction-meta">
          <span v-if="attraction.rating" class="meta-item rating">
            <span class="star">★</span>{{ attraction.rating }}
          </span>
          <span class="meta-item">
            <span class="meta-icon">⏱</span>{{ attraction.visit_duration }}分钟
          </span>
        </div>
        <p class="attraction-address">{{ attraction.address }}</p>
        <p v-if="attraction.open_hours" class="attraction-detail">
          <span class="detail-icon">🕐</span>{{ attraction.open_hours }}
        </p>
        <p v-if="attraction.tel" class="attraction-detail">
          <span class="detail-icon">📞</span>
          <a v-if="isCoarsePointer" class="tel-link" :href="`tel:${attraction.tel}`">{{ attraction.tel }}</a>
          <span v-else>{{ attraction.tel }}</span>
        </p>
        <p class="attraction-desc">{{ attraction.description }}</p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Attraction } from '@/types'

const props = defineProps<{
  attraction: Attraction
  globalIndex: number
  editMode?: boolean
  photoUrl?: string
}>()

const isCoarsePointer = computed(() => {
  return typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches
})

const imageUrl = computed(() => {
  if (props.photoUrl) return props.photoUrl
  if (props.attraction.image_url) return props.attraction.image_url
  const colors = [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#43e97b', end: '#38f9d7' },
    { start: '#fa709a', end: '#fee140' }
  ]
  const idx = props.globalIndex % colors.length
  const { start, end } = colors[idx]
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
    <defs>
      <linearGradient id="grad${idx}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${start};stop-opacity:1" />
        <stop offset="100%" style="stop-color:${end};stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="300" fill="url(#grad${idx})"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold" fill="white">${props.attraction.name}</text>
  </svg>`
  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
})

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}
</script>

<style scoped>
.attraction-card {
  background: var(--white);
  border-radius: 0;
  overflow: hidden;
  border: var(--border-main) solid var(--border);
  box-shadow: var(--shadow-main);
  transition: all var(--transition-fast);
  position: relative;
}

.attraction-card:hover {
  transform: translateY(-2px);
  box-shadow: 8px 8px 0px 0px var(--border);
}

/* 右上角红色装饰 */
.attraction-card::after {
  content: '';
  position: absolute;
  top: 12px;
  right: 12px;
  width: 12px;
  height: 12px;
  border: 2px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--primary-red);
  z-index: 10;
}

.attraction-image-wrapper {
  position: relative;
  overflow: hidden;
}

.attraction-image {
  width: 100%;
  height: 180px;
  object-fit: cover;
  transition: transform var(--transition-slow);
  display: block;
}

.attraction-card:hover .attraction-image {
  transform: scale(1.05);
}

.attraction-badge {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  background: var(--color-gradient);
  color: var(--color-text-inverse);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-circle);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-sm);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.price-tag {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  background: var(--color-error);
  color: var(--color-text-inverse);
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-sm);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.category-tag {
  position: absolute;
  bottom: var(--space-2);
  left: var(--space-2);
  background: rgba(0, 0, 0, 0.5);
  color: var(--color-text-inverse);
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-xs);
  backdrop-filter: blur(4px);
}

.attraction-body {
  padding: var(--space-4);
}

.attraction-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-black);
  text-transform: uppercase;
  color: var(--foreground);
  margin: 0 0 var(--space-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.05em;
}

.attraction-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.meta-item.rating {
  color: #faad14;
}

.star {
  color: #faad14;
}

.meta-icon {
  font-size: var(--font-size-xs);
}

.attraction-address {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0 0 var(--space-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attraction-detail {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0 0 var(--space-2);
  display: flex;
  align-items: flex-start;
  gap: 4px;
  line-height: var(--line-height-relaxed);
}

.detail-icon {
  flex-shrink: 0;
}

.tel-link {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.attraction-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: var(--line-height-relaxed);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.edit-field {
  margin-bottom: var(--space-2);
}

.edit-field label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
</style>
