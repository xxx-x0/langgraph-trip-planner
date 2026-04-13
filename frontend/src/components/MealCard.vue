<template>
  <div class="meal-card" :class="[`source-${meal.source || 'default'}`]">
    <div class="meal-header">
      <span class="meal-type-badge">{{ getMealLabel(meal.type) }}</span>
      <span v-if="meal.cuisine" class="meal-cuisine-tag">{{ meal.cuisine }}</span>
      <span v-if="meal.source === 'nearby'" class="source-badge nearby">📍 附近</span>
      <span v-else-if="meal.source === 'popular'" class="source-badge popular">🔥 热门</span>
    </div>
    <div class="meal-name">{{ meal.name }}</div>
    <div class="meal-details">
      <span v-if="meal.rating" class="detail-item">
        <span class="detail-star">★</span>{{ meal.rating }}
      </span>
      <span v-if="meal.avg_cost" class="detail-item price">¥{{ meal.avg_cost }}/人</span>
      <span v-if="meal.distance" class="detail-item">📏 {{ meal.distance }}</span>
    </div>
    <div v-if="meal.address" class="meal-address">📍 {{ meal.address }}</div>
    <div v-if="meal.description" class="meal-desc">{{ meal.description }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Meal } from '@/types'

defineProps<{
  meal: Meal
}>()

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  }
  return labels[type] || type
}
</script>

<style scoped>
.meal-card {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  box-shadow: var(--shadow-card);
  border: 1px solid var(--color-border-light);
  transition: all var(--transition-normal);
}

.meal-card:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}

.meal-card.source-nearby {
  border-left: 3px solid var(--color-meal-nearby);
}

.meal-card.source-popular {
  border-left: 3px solid var(--color-meal-popular);
}

.meal-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}

.meal-type-badge {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-inverse);
  background: var(--color-gradient);
}

.meal-cuisine-tag {
  display: inline-block;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  background: var(--color-warning-bg);
  border: 1px solid rgba(250, 173, 20, 0.2);
}

.source-badge {
  display: inline-block;
  padding: 1px var(--space-2);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.source-badge.nearby {
  color: var(--color-meal-nearby);
  background: var(--color-success-bg);
}

.source-badge.popular {
  color: var(--color-meal-popular);
  background: var(--color-error-bg);
}

.meal-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.meal-details {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.detail-star {
  color: #faad14;
}

.detail-item.price {
  color: var(--color-warning);
  font-weight: var(--font-weight-medium);
}

.meal-address {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meal-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: var(--line-height-relaxed);
}
</style>
