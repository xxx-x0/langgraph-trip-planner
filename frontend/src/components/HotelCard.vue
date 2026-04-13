<template>
  <div class="hotel-card">
    <div class="hotel-header">
      <div class="hotel-icon">🏨</div>
      <div class="hotel-title-area">
        <h4 class="hotel-name">{{ hotel.name }}</h4>
        <span v-if="hotel.type" class="hotel-type">{{ hotel.type }}</span>
      </div>
      <div v-if="hotel.rating" class="hotel-rating">
        <span class="rating-score">{{ hotel.rating }}</span>
        <span class="rating-stars">{{ getStars(Number(hotel.rating)) }}</span>
      </div>
    </div>
    <div class="hotel-body">
      <div class="hotel-info-grid">
        <div class="info-item">
          <span class="info-icon">📍</span>
          <span class="info-text">{{ hotel.address }}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">💰</span>
          <span class="info-text price">{{ hotel.price_range }}</span>
        </div>
        <div class="info-item">
          <span class="info-icon">📏</span>
          <span class="info-text">{{ hotel.distance }}</span>
        </div>
        <div v-if="hotel.estimated_cost" class="info-item">
          <span class="info-icon">💵</span>
          <span class="info-text price">约¥{{ hotel.estimated_cost }}/晚</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Hotel } from '@/types'

defineProps<{
  hotel: Hotel
}>()

const getStars = (rating: number): string => {
  const full = Math.floor(rating)
  const half = rating % 1 >= 0.5 ? 1 : 0
  return '★'.repeat(full) + (half ? '☆' : '') + '☆'.repeat(Math.max(0, 5 - full - half))
}
</script>

<style scoped>
.hotel-card {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-card);
  border: 1px solid var(--color-border-light);
  transition: all var(--transition-normal);
}

.hotel-card:hover {
  box-shadow: var(--shadow-card-hover);
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

.hotel-type {
  display: inline-block;
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: 1px var(--space-2);
  border-radius: var(--radius-pill);
  margin-top: 4px;
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
  color: var(--color-primary);
}

.rating-stars {
  font-size: var(--font-size-xs);
  color: #faad14;
  letter-spacing: 1px;
}

.hotel-body {
  padding: 0 var(--space-4) var(--space-4);
}

.hotel-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

.info-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
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
  color: var(--color-warning);
  font-weight: var(--font-weight-medium);
}
</style>
