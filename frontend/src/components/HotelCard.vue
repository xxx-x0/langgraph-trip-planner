<template>
  <div class="hotel-card">
    <!-- 酒店图片 -->
    <div class="hotel-image-wrapper">
      <img :src="imageUrl" :alt="hotel.name" class="hotel-image" @error="handleImageError" />
    </div>

    <div class="hotel-header">
      <div class="hotel-icon">🏨</div>
      <div class="hotel-title-area">
        <h4 class="hotel-name">{{ hotel.name }}</h4>
        <div class="hotel-tags">
          <span v-if="hotel.type" class="hotel-type">{{ hotel.type }}</span>
          <span v-if="hotel.star_rating" class="hotel-star-badge">
            {{ getStarRatingText(hotel.star_rating) }}
          </span>
        </div>
      </div>
      <div v-if="hotel.rating || hotel.star_rating" class="hotel-rating">
        <span v-if="hotel.rating" class="rating-score">{{ hotel.rating }}</span>
        <span v-if="hotel.star_rating" class="rating-stars">{{ getStars(hotel.star_rating) }}</span>
      </div>
    </div>

    <div class="hotel-body">
      <!-- 地址 -->
      <div class="info-item address-item">
        <span class="info-icon">📍</span>
        <span class="info-text">{{ hotel.address }}</span>
      </div>

      <!-- 价格区域 -->
      <div class="hotel-price-section">
        <div v-if="hotel.price" class="price-main">
          <span class="price-currency">{{ hotel.currency || 'CNY' }}</span>
          <span class="price-value">¥{{ Math.round(hotel.price) }}</span>
          <span class="price-unit">/晚</span>
          <span v-if="hotel.original_price && hotel.original_price > hotel.price" class="price-original">
            ¥{{ Math.round(hotel.original_price) }}
          </span>
          <span v-if="hotel.original_price && hotel.original_price > hotel.price" class="price-save">
            省¥{{ Math.round(hotel.original_price - hotel.price) }}
          </span>
        </div>
        <div v-else-if="hotel.price_range" class="price-main">
          <span class="info-text price">{{ hotel.price_range }}</span>
        </div>
        <div v-if="hotel.estimated_cost && !hotel.price" class="price-estimated">
          约¥{{ hotel.estimated_cost }}/晚
        </div>
      </div>

      <!-- 距离 -->
      <div class="info-item">
        <span class="info-icon">📏</span>
        <span class="info-text">{{ hotel.distance }}</span>
        <span v-if="hotel.distance_in_meters" class="distance-meters">
          ({{ formatDistance(hotel.distance_in_meters) }})
        </span>
      </div>

      <!-- 设施标签 -->
      <div v-if="hotel.hotel_amenities && hotel.hotel_amenities.length > 0" class="amenities-section">
        <div class="amenities-label">设施</div>
        <div class="amenities-tags">
          <span
            v-for="amenity in hotel.hotel_amenities.slice(0, 6)"
            :key="amenity"
            class="amenity-tag"
          >
            {{ amenity }}
          </span>
        </div>
      </div>

      <!-- 房间设施 -->
      <div v-if="hotel.room_amenities && hotel.room_amenities.length > 0" class="amenities-section">
        <div class="amenities-label">房间</div>
        <div class="amenities-tags">
          <span
            v-for="amenity in hotel.room_amenities.slice(0, 4)"
            :key="amenity"
            class="amenity-tag room-tag"
          >
            {{ amenity }}
          </span>
        </div>
      </div>

      <!-- 详细描述 -->
      <div v-if="hotel.description" class="description-section">
        <div class="description-content" :class="{ expanded: isDescExpanded }">
          {{ hotel.description }}
        </div>
        <button
          v-if="hotel.description.length > 80"
          class="desc-toggle"
          @click="isDescExpanded = !isDescExpanded"
        >
          {{ isDescExpanded ? '收起' : '展开' }}
        </button>
      </div>

      <!-- 操作按钮 -->
      <div v-if="hotel.detail_url" class="hotel-actions">
        <a
          :href="hotel.detail_url"
          target="_blank"
          rel="noopener noreferrer"
          class="detail-link"
        >
          查看详情 →
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Hotel } from '@/types'

const props = defineProps<{
  hotel: Hotel
}>()

const isDescExpanded = ref(false)

const imageUrl = computed(() => {
  if (props.hotel.image_url) return props.hotel.image_url
  const name = props.hotel.name || '酒店'
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
    <defs>
      <linearGradient id="hg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
        <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="200" fill="url(#hg)"/>
    <text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold" fill="white">${name}</text>
    <text x="50%" y="65%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="14" fill="rgba(255,255,255,0.7)">🏨</text>
  </svg>`
  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
})

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="200"%3E%3Crect width="400" height="200" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="16" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}

const getStars = (rating: number): string => {
  const full = Math.floor(rating)
  const half = rating % 1 >= 0.5 ? 1 : 0
  return '★'.repeat(full) + (half ? '☆' : '') + '☆'.repeat(Math.max(0, 5 - full - half))
}

const getStarRatingText = (rating: number): string => {
  if (rating >= 5) return '五星级'
  if (rating >= 4.5) return '豪华型'
  if (rating >= 4) return '四星级'
  if (rating >= 3.5) return '高档型'
  if (rating >= 3) return '三星级'
  return '经济型'
}

const formatDistance = (meters: number): string => {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)}km`
  }
  return `${meters}m`
}
</script>

<style>
.hotel-card {
  background: #ffffff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: rgba(0, 0, 0, 0.02) 0px 0px 0px 1px, rgba(0, 0, 0, 0.04) 0px 2px 6px, rgba(102, 126, 234, 0.06) 0px 4px 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.hotel-card:hover {
  box-shadow: rgba(0, 0, 0, 0.02) 0px 0px 0px 1px, rgba(0, 0, 0, 0.06) 0px 4px 12px, rgba(102, 126, 234, 0.1) 0px 8px 24px;
}
</style>

<style scoped>
.hotel-image-wrapper {
  width: 100%;
  height: 160px;
  overflow: hidden;
  background: #f5f5f5;
}

.hotel-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.hotel-card:hover .hotel-image {
  transform: scale(1.03);
}

.hotel-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4) var(--space-2);
}

.hotel-icon {
  font-size: var(--font-size-3xl);
  flex-shrink: 0;
}

.hotel-title-area {
  flex: 1;
  min-width: 0;
}

.hotel-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hotel-tags {
  display: flex;
  gap: var(--space-1);
  margin-top: 4px;
  flex-wrap: wrap;
}

.hotel-type {
  display: inline-block;
  font-size: var(--font-size-xs);
  color: #667eea;
  background: #f0f3ff;
  padding: 1px var(--space-2);
  border-radius: 9999px;
}

.hotel-star-badge {
  display: inline-block;
  font-size: var(--font-size-xs);
  color: #faad14;
  background: #fffbe6;
  padding: 1px var(--space-2);
  border-radius: 9999px;
}

.hotel-rating {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
}

.rating-score {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: #667eea;
}

.rating-stars {
  font-size: var(--font-size-xs);
  color: #faad14;
  letter-spacing: 1px;
}

.hotel-body {
  padding: 0 var(--space-4) var(--space-4);
}

.info-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
}

.address-item .info-text {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  line-height: 1.5;
}

.info-icon {
  font-size: var(--font-size-sm);
  flex-shrink: 0;
}

.info-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-text.price {
  color: #faad14;
  font-weight: var(--font-weight-medium);
}

.hotel-price-section {
  margin-bottom: var(--space-2);
}

.price-main {
  display: flex;
  align-items: baseline;
  gap: 4px;
  flex-wrap: wrap;
}

.price-currency {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.price-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: #faad14;
}

.price-unit {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.price-original {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  text-decoration: line-through;
}

.price-save {
  font-size: var(--font-size-xs);
  color: #52c41a;
  background: #f6ffed;
  padding: 0 6px;
  border-radius: 4px;
}

.price-estimated {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.distance-meters {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-left: 4px;
}

.amenities-section {
  margin-bottom: var(--space-2);
}

.amenities-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}

.amenities-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.amenity-tag {
  font-size: var(--font-size-xs);
  color: #667eea;
  background: #f0f3ff;
  padding: 2px 8px;
  border-radius: 9999px;
  white-space: nowrap;
}

.room-tag {
  color: #52c41a;
  background: #f6ffed;
}

.description-section {
  margin-bottom: var(--space-2);
}

.description-content {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.description-content.expanded {
  -webkit-line-clamp: unset;
  display: block;
}

.desc-toggle {
  font-size: var(--font-size-xs);
  color: #667eea;
  background: none;
  border: none;
  padding: 0;
  margin-top: 4px;
  cursor: pointer;
}

.desc-toggle:hover {
  text-decoration: underline;
}

.hotel-actions {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.detail-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: #667eea;
  text-decoration: none;
  font-weight: var(--font-weight-medium);
}

.detail-link:hover {
  text-decoration: underline;
}
</style>
